#!/usr/bin/env bash
# decoupledMigrate.sh
#
# Given a list of organization/repository pairs, this script will perform all post migration tasks on these repositories
# in GitHub Enterprise Cloud. Use this after migrating a repository using [ECI](https://eci.github.com) to migrate a repo.
#
# Usage:
#    scripts/decoupledMigrate.sh < data/repoList.txt

################## Required Environment Variables ####################
# export GH_PAT=<The Personal Access Token from GHEC>
# export GH_SOURCE_PAT=<The Personal Access Token from GHES>
################## Optional Environment Variables ####################
# export GH_ORG=<GHEC destination org for the repos to be migrated>
# export SKIP_ARCHIVE=true

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
DEBUG=${DEBUG:-false}
$DEBUG && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

# Credit to http://stackoverflow.com/a/246128/424301
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$DIR/.."
SCRIPTS_DIR="$BASE_DIR/scripts"
DATA_DIR="$DIR/../data/migrations"
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

unset GH_TOKEN # Ditch this one as it interferes with using gh cli in subtle ways

GH_PAT=${GH_PAT:?You must specify a Personal Access Token from GHEC in the GH_PAT environment variable}
GH_SOURCE_PAT=${GH_SOURCE_PAT:?You must specify a Personal Access Token from GHES in the GH_SOURCE_PAT environment variable}

GH_SOURCE_HOST=${GH_SOURCE_HOST:-github.example.com}
GH_ORG=${GH_ORG:-}
SKIP_ARCHIVE=${SKIP_ARCHIVE:-false}

CRON_RENEW_VAULT_TOKEN="$SCRIPTS_DIR/cronRenewVaultToken.sh"

TS=$(iso8601_win_safe_ts)

REPO_ID_MAP_FILE="$DATA_DIR/repoIDMap-$TS.csv"
WEBHOOK_MAP_FILE="$DATA_DIR/webhookMap-$TS.txt"

assertModernBash
assertJqInstalled
assertParallelInstalled
assertInVirtualenv
useSystemCAForPython

# Create a temp file and force remove it at exit
scratch=$(mktemp -t migrate.XXXXXXXXXX)
function finish {
    removeCrontab "$CRON_RENEW_VAULT_TOKEN"
    rm -rf "$scratch"
}
trap finish EXIT


mkdir -p "$DATA_DIR"
cd "$DATA_DIR"


promptForVaultTokenIfExpired

setCrontab "$CRON_RENEW_VAULT_TOKEN"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

sourceRepos=()
inputLines=()
declare -A repoIDMap

gh auth login \
    --hostname "$GH_SOURCE_HOST" \
    --with-token \
    <<< "$GH_SOURCE_PAT"
gh auth login \
    --hostname github.com \
    --with-token \
    <<< "$GH_PAT"

## Read in all the repos from STDIN, and
## validate they are present on the source,
## and skip and warn if they are already present on the destination
while IFS= read -r line && [[ -n "$line" ]]  ; do
    # Ignore comment lines
    if grep '^#' <<<"$line"; then
        log DEBUG "Ignoring comment $line"
        continue
    fi
    inputLines+=("$line")
done

if [[ ${#inputLines[*]} -eq 0 ]]; then
    log ERROR "No repositories requiring migration passed via STDIN, please pass org/repo pairs in STDIN"
    log INFO "Usage: ./scripts/decoupledMigrate.sh < data/repoList.txt"
    exit 1
fi
if [[ "$GH_ORG" = "${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}"  ]]; then
    matchingRepo=$(printf "%s\n" "${inputLines[@]}" | sed 's#.*/##' | sort | uniq -d)
    set +e
    result=$(printf "%s\n" "${inputLines[@]}" | grep -E "/${matchingRepo}"'$')
    set -e
    if [ -z "$result" ]; then
        # shellcheck disable=SC2207
        UNIQ_REPOS=($(printf "%s\n" "${inputLines[@]}" | sort -u))
    else
        log ERROR "Repo duplicated in input: $(tr "\n" " " <<<"$result")"
        exit 1
    fi
else
    # shellcheck disable=SC2207
    UNIQ_REPOS=($(printf "%s\n" "${inputLines[@]}" | sort -u))
fi

for line in "${UNIQ_REPOS[@]}"; do
    log INFO "Checking $line"
    ghSourceUrl="https://$GH_SOURCE_HOST/$line"
    ghSourceOrg=$(cut -d/ -f1 <<<"$line")
    repo=$(cut -d/ -f2 <<<"$line")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    ghTargetUrl="https://github.com/$ghTargetOrg/$repo"
    if gh repo view "$ghTargetUrl" --json name > /dev/null; then
        # Check if repo exists already, warn and skip if not.
        log INFO "Repo $ghTargetUrl corresponding to $ghSourceUrl found: adding to list"
        sourceRepos+=("$line")
    else
        log ERROR "Repo $ghTargetUrl corresponding to $ghSourceUrl not found"
        exit 1
    fi
    rateLimitSleep
done

# Create repository map file and webhook map file
log INFO "Creating mapping file $WEBHOOK_MAP_FILE"

for line in "${sourceRepos[@]}"; do
    ghSourceOrg=$(cut -d/ -f1 <<<"$line")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    repo=$(cut -d/ -f2 <<<"$line")

    log INFO "Extracted org $ghSourceOrg and repo $repo from $line"

    # GitHub CLI api
    # https://cli.github.com/manual/gh_api
    # Extracting the current visibility and ID of the repo
    rateLimitSleep
    api_response=$(gh api --hostname "$GH_SOURCE_HOST" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "/repos/$ghSourceOrg/$repo")
    topics=$(gh api \
        --hostname "$GH_SOURCE_HOST" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "/repos/$ghSourceOrg/$repo/topics")
    # shellcheck disable=SC2034
    repoVisibility=$(jq -r '.visibility' <<<"$api_response")
    # shellcheck disable=SC2034
    repoId=$(jq -r '.id' <<<"$api_response")

    existingTopicArchive=$(jq -r '.names[] | select(. | startswith("github-cloud-migrat")) | select(. | endswith("archive"))' <<<"$topics")
    echo "$ghSourceOrg/$repo,$ghTargetOrg/$repo" >> "$WEBHOOK_MAP_FILE"

    repoIDMap["$line", "GHES"]=$repoId

    newrepoId=$(gh api \
        --hostname github.com \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "/repos/$ghTargetOrg/$repo" \
        | jq -r '.id')
    repoIDMap["$line", "GHEC"]=$newrepoId
    # Archive Source repo
    archive_repo "true"
    if [ -n "$existingTopicArchive" ]; then
        # Archive destination repo
        archive_repo "true" "github.com" "$ghTargetOrg"
     else
        #Unarchive destination repo
        archive_repo "false" "github.com" "$ghTargetOrg"
    fi

done

## Capture the ID of the repos in GHES and GHEC
cat /dev/null > "$REPO_ID_MAP_FILE"
for key in "${!repoIDMap[@]}"; do
    ghSourceOrg=$(cut -d/ -f1 <<<"$key")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    repo=$(cut -d/ -f2 <<<"$key")
    echo "$ghSourceOrg,$repo,${repoIDMap[$key]}" >> "$REPO_ID_MAP_FILE"
done
call_post_migration_scripts "$WEBHOOK_MAP_FILE"
