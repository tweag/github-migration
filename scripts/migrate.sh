#!/usr/bin/env bash
# migrate.sh
#
# Given a list of organization/repository pairs, this script will migrate those repositories
# from GitHub Enterprise Server to GitHub Enterprise Cloud.
#
# Usage:
#    scripts/migrate.sh < data/repoList.txt

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
DEBUG=${DEBUG:-false}
$DEBUG && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

# Only show verbose output if DEBUG=true
if $DEBUG; then
    VERBOSE='--verbose'
else
    VERBOSE=''
fi

# Credit to http://stackoverflow.com/a/246128/424301
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$DIR/.."
SCRIPTS_DIR="$BASE_DIR/scripts"
DATA_DIR="$DIR/../data/migrations"
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"


################## Required Environment Variables ####################
# export GH_PAT=<The Personal Access Token from GHEC>
# export GH_SOURCE_PAT=<The Personal Access Token from GHES>
# export AZURE_STORAGE_CONNECTION_STRING=<valid Azure Storage Connection String for an Azure Blob Storage>
################## Optional Environment Variables ####################
# export GH_ORG=<GHEC destination org for the repos to be migrated>
# export SKIP_ARCHIVE=true

unset GH_TOKEN # Ditch this one as it interferes with using gh cli in subtle ways

GH_PAT=${GH_PAT:?You must specify a Personal Access Token from GHEC in the GH_PAT environment variable}
GH_SOURCE_PAT=${GH_SOURCE_PAT:?You must specify a Personal Access Token from GHES in the GH_SOURCE_PAT environment variable}
AZURE_STORAGE_CONNECTION_STRING=${AZURE_STORAGE_CONNECTION_STRING:? You must specify a valid Azure Storage Connection String for an Azure Blob Storage in the AZURE_STORAGE_CONNECTION_STRING environment variable.}

GH_SOURCE_HOST=${GH_SOURCE_HOST:-github.example.com}
GH_ORG=${GH_ORG:-}
REPO_SUFFIX=${REPO_SUFFIX:-}
SKIP_ARCHIVE=${SKIP_ARCHIVE:-false}

CRON_RENEW_VAULT_TOKEN="$SCRIPTS_DIR/cronRenewVaultToken.sh"

TS=$(iso8601_win_safe_ts)

WEBHOOK_MAP_FILE="$DATA_DIR/webhookMap-$TS.txt"
REPO_ID_MAP_FILE="$DATA_DIR/repoIDMap-$TS.csv"
MIGRATED_FILE="$DATA_DIR/migrated-OK-$TS.txt"
ERROR_FILE="$DATA_DIR/migrated-ERROR-$TS.txt"

assertModernBash
assertJqInstalled
assertParallelInstalled
assertGhCliInstalled
assertInVirtualenv
useSystemCAForPython

# Create a temp file and force remove it at exit
scratch=$(mktemp -t migrate.XXXXXXXXXX)
function finish {
    removeCrontab "$CRON_RENEW_VAULT_TOKEN"
    rm -rf "$scratch"
}
trap finish EXIT

#Add color if stdout is a terminal
# Thanks https://serverfault.com/a/753459
if [[ -t 1 ]]; then
    YELLOW="\033[1;33m"
    NOCOLOR="\033[0m"
else
    YELLOW=""
    NOCOLOR=""
fi

# Ensure we have a valid Vault token token before proceeding
promptForVaultTokenIfExpired
setCrontab "$CRON_RENEW_VAULT_TOKEN"

# Check that the gei extension for the GitHub CLi is installed
if ! gh gei help > /dev/null 2>&1; then
    log ERROR "No command 'gh gei' found, please install per https://github.com/github/gh-gei"
    exit 1
fi

log INFO "$0 - migrate repositories from $GH_SOURCE_HOST"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"


renewSelfVaultToken


log INFO "$0 - migrate repositories from $GH_SOURCE_HOST"

Succeeded=0
Failed=0
sourceRepos=()
migratedRepos=()
errorRepos=()
inputLines=()
orgNames=()
declare -A RepoMigrations
declare -A repoIDMap
declare -A sourceOrgMap
declare -A targetOrgMap


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
while IFS= read -r line; do
    # Ignore comment lines
    if grep '^#' > /dev/null 2>&1 <<<"$line"; then
        log DEBUG "Ignoring comment $line"
        continue
    # Thanks https://stackoverflow.com/a/4233691
    elif  grep '^[[:space:]]*$' > /dev/null 2>&1 <<<"$line"; then
        log DEBUG "Ignoring blank line"
        continue
    fi
    inputLines+=("$line")
done

if [[ ${#inputLines[*]} -eq 0 ]]; then
    log ERROR "No repositories requiring migration passed via STDIN, please pass org/repo pairs in STDIN"
    log INFO "Usage: ./scripts/migrate.sh < data/repoList.txt"
    exit 1
fi
if [[ "$GH_ORG" = "${GHEC_PREFIX}-${GHEC_ORG_SUFFIX}"  ]]; then
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
    targetRepo="$repo$REPO_SUFFIX"

    #Query repo details from the source
    repoDetails=$(gh repo view "$ghSourceUrl" --json name 2> /dev/null)

    #Reject if repository has been renamed
    ghSourceRepo=$(jq -r '.name' <<< "$repoDetails")

    if [ "$repo" != "$ghSourceRepo" ]; then
        log ERROR "Repo $repo has been renamed to $ghSourceRepo"
	exit 1
    fi

    if [ "$repoDetails" ]; then

	# Check if repo exists already, warn and skip if not.
        ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
        ghTargetUrl="https://github.com/$ghTargetOrg/$targetRepo"
        if GH_HOST=github.com gh repo view "$ghTargetUrl" --json name > /dev/null; then
            log WARN "Skipping Repo $ghSourceOrg/$repo - it already exists at $ghTargetUrl"
            continue
        else
            log INFO "Repo $ghSourceUrl found, $ghTargetUrl not found: adding to migration list"
            sourceRepos+=("$line")
            # Add organization name to the orgNames array
            orgNames+=("$ghSourceOrg")
        fi
    else
        log ERROR "Repo $ghSourceUrl not found"
        exit 1
    fi
    rateLimitSleep
done

#Validate if user is owner of source and target Organizations
log INFO "Validating PAT token for organizations"
#
uniqOrgNames=$(printf "%s\n" "${orgNames[@]}" | sort -u )

# shellcheck disable=SC2068
for orgName in $uniqOrgNames; do
	targetOrg="$(getTargetOrg "$orgName")"
	log INFO "Validating GHES org ownership"
	assertOrganizationOwner "$GH_SOURCE_PAT" "$orgName" "https://github.example.com/api/v3"
	log INFO "Validating GHEC org ownership"
	assertOrganizationOwner "$GH_PAT" "$targetOrg"
	log INFO "Validation of PAT tokens successful"
done

# Queue migrations, while preserving and transforming target
# repository visibility as appropriate (public->internal)
migration=0
for line in "${sourceRepos[@]}"; do
    ((migration++)) || true
    # Split into org and repo
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

    repoVisibility=$(jq -r '.visibility' <<<"$api_response")
    repoId=$(jq -r '.id' <<<"$api_response")

    repoArchived=$(jq -r '.archived' <<<"$api_response")
    if [ "$repoArchived" = "false" ]; then
        newTopicPreMigration="github-cloud-migrating"
    else
        newTopicPreMigration="github-cloud-migrating-archive"
    fi
    check_and_replace_topic "$newTopicPreMigration" "true" "$repo" "$ghSourceOrg"
    # Archive Source repo
    archive_repo "true"

    targetRepoVisibility=""
    if [ "$repoVisibility" = "public" ]; then
        targetRepoVisibility="internal"
    else
        targetRepoVisibility="$repoVisibility"
    fi

    # Queuing repo migrations


    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    targetRepo="$repo$REPO_SUFFIX"
    log INFO "Targeting $ghTargetOrg/$targetRepo as destination"
    rateLimitSleep

    log INFO "${YELLOW}Queueing migration for $line: ${migration} of ${#sourceRepos[@]} - $(( migration * 100 / ${#sourceRepos[@]} ))%${NOCOLOR}"

    if gh gei migrate-repo \
        --github-source-org "$ghSourceOrg" \
        --source-repo "$repo" \
        --github-target-org "$ghTargetOrg" \
        --target-repo "$targetRepo"  \
        --ghes-api-url "https://$GH_SOURCE_HOST/api/v3" \
        --queue-only \
        --target-repo-visibility "$targetRepoVisibility" \
        $VERBOSE \
        | tee "$scratch"; then

        MigrationID=$(grep -o 'migration (ID: [^)]*' < "$scratch" \
            | sed 's/migration (ID: //')
        if [ -z "$MigrationID" ]
        then
            log ERROR "Migration failed, no migration ID detected for repo: $ghSourceOrg/$repo"
            errorRepos+=("$line")
            ((Failed++)) || true
        else
            log INFO "Migration ID for repo $ghSourceOrg/$repo is:  $MigrationID"
            RepoMigrations[$line]=$MigrationID
            repoIDMap["$line", "GHES"]=$repoId
            # I am not 100% sure we re going to use these but will quiet shellcheck about it
            #shellcheck disable=SC2034
            sourceOrgMap["$ghSourceOrg"]="$ghTargetOrg"
            #shellcheck disable=SC2034
            targetOrgMap["$ghTargetOrg"]="$ghTargetOrg"
            echo "$ghSourceOrg/$repo,$ghTargetOrg/$repo$REPO_SUFFIX" >> "$WEBHOOK_MAP_FILE"
        fi
    else
        log ERROR "Migration failed, could not queue migration for repo: $ghSourceOrg/$repo"
        errorRepos+=("$line")
        ((Failed++)) || true
    fi

done


# Wait for migrations to be completed
for key in "${!RepoMigrations[@]}"; do
    ghSourceOrg=$(cut -d/ -f1 <<<"$key")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    repo=$(cut -d/ -f2 <<<"$key")
    targetRepo="$repo$REPO_SUFFIX"
    log INFO "${YELLOW}Waiting for migration of $key: $(( Succeeded + Failed )) of ${#RepoMigrations[@]} - $(( (Succeeded + Failed ) * 100 / ${#RepoMigrations[@]} ))%${NOCOLOR}"
    if gh gei wait-for-migration \
        --migration-id "${RepoMigrations[$key]}"; then
        log INFO "Getting new repo ID for $key"
        newrepoId=$(gh api \
           --hostname github.com \
           -H "Accept: application/vnd.github+json" \
           -H "X-GitHub-Api-Version: 2022-11-28" \
           "/repos/$ghTargetOrg/$targetRepo" \
           | jq -r '.id')
        repoIDMap["$key", "GHEC"]=$newrepoId
        topics=$(gh api \
            --hostname "$GH_SOURCE_HOST" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            "/repos/$ghSourceOrg/$repo/topics")
        existingTopicArchive=$(jq -r '.names[] | select(. | startswith("github-cloud-migrat")) | select(. | endswith("archive"))' <<<"$topics")
        if [ -n "$existingTopicArchive" ]; then
            # Archive destination repo
            archive_repo "true" "github.com" "$ghTargetOrg" "$targetRepo"
        else
            #Unarchive destination repo
            archive_repo "false" "github.com" "$ghTargetOrg" "$targetRepo"
        fi
        ((Succeeded++)) || true
        migratedRepos+=("$key")
    else
        ((Failed++)) || true
        errorRepos+=("$key")
    fi
done

for line in "${migratedRepos[@]}"; do
    # Write to file
    echo "$line" >> "$MIGRATED_FILE"
done

for line in "${errorRepos[@]}"; do
    # Write to file
    echo "$line" >> "$ERROR_FILE"
done

log INFO "Creating repository mapping file $REPO_ID_MAP_FILE"

echo "Source Organization,Repository Name,GHEC or GHES,repo ID" > "$REPO_ID_MAP_FILE"
## Capture the ID of the repos in GHES and GHEC
cat /dev/null > "$REPO_ID_MAP_FILE"
for key in "${!repoIDMap[@]}"; do
    ghSourceOrg=$(cut -d/ -f1 <<<"$key")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    repo=$(cut -d/ -f2 <<<"$key")
    echo "$ghSourceOrg,$repo,${repoIDMap[$key]}" >> "$REPO_ID_MAP_FILE"
done

if [[ "$Succeeded" -gt 0 ]]; then log INFO "List of migrated repos:  $MIGRATED_FILE"; fi
if [[ "$Failed" -gt 0 ]]; then log INFO "List of errored repos: $ERROR_FILE"; fi

# Create repository map file and webhook map file
if [[ $Succeeded -gt 0 ]]; then
    promptForVaultTokenIfExpired
    call_post_migration_scripts "$WEBHOOK_MAP_FILE"
fi

log INFO "============== Summary ==============="
log INFO "Total number of successful migrations: $Succeeded"
log INFO "Total number of failed migrations: $Failed"

if [ "$Failed" -gt 0 ]; then
    exit 1
fi
