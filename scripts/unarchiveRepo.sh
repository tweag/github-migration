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
VAULT_TOKEN=${VAULT_TOKEN:?You must specify a Vault token in the VAULT_TOKEN environment variable.}

GH_SOURCE_HOST=${GH_SOURCE_HOST:-github.example.com}
GH_ORG=${GH_ORG:-}
SKIP_ARCHIVE=${SKIP_ARCHIVE:-false}


assertModernBash
assertJqInstalled
assertParallelInstalled
assertInVirtualenv
useSystemCAForPython

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

inputLines=()

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
    log ERROR "No repositories requiring unarchving passed via STDIN, please pass org/repo pairs in STDIN"
    log INFO "Usage: ./scripts/unarchiveRepo.sh < data/repoList.txt"
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
    ghSourceOrg=$(cut -d/ -f1 <<<"$line")
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

    # shellcheck disable=SC2034
    repoVisibility=$(jq -r '.visibility' <<<"$api_response")
    # shellcheck disable=SC2034
    repoId=$(jq -r '.id' <<<"$api_response")
    repoArchived=$(jq -r '.archived' <<<"$api_response")

    # Archive Source repo
    if [[ "$repoArchived" = "true"  ]]; then
        archive_repo "false"
    fi
done
