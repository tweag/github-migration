#!/usr/bin/env bash
# common.sh
#
# Common functions
# Include this from other scripts
#
# Usage:
#    #shellcheck disable=SC1090,SC1091
#    source "$SCRIPTS_DIR/common.sh"

SCRIPTS_DIR=${SCRIPTS_DIR:-$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )}
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$DIR/.."
MIGRATE_WEBHOOK="$SCRIPTS_DIR/migrateWebhook.py"
MIGRATE_PERMISSIONS="$SCRIPTS_DIR/migratePermissions.py"
MIGRATE_LFS="$SCRIPTS_DIR/migrateLfs.sh"
MIGRATE_GATOR_PULL_REQUESTS="$SCRIPTS_DIR/migrateGatorPullRequests.py"
PATCH_BUILDKITE_PIPELINE="$SCRIPTS_DIR/patchBuildkitePipeline.py"
MIGRATE_APP_REPO_PERMISSION="$SCRIPTS_DIR/migrateAppPermission.py"
UPDATE_REPO_DESC="$SCRIPTS_DIR/updateRepoDescription.py"
MIGRATE_GH_PAGES="$SCRIPTS_DIR/migrateGhPages.py"

LFS_FILE="$BASE_DIR/data/lfsRepos.txt"
GHES_API_URL="https://github.example.com/api/v3"
GHEC_API_URL="https://api.github.com"
GH_SOURCE_HOST=${GH_SOURCE_HOST:-github.example.com}

# Set this to the prefix that all your enterprise repositories share
GHEC_PREFIX="example"
# Set this to the suffix that all your enterprise managed users share
GHEC_SUFFIX="example"
GHEC_SANDBOX_ORG="${GHEC_PREFIX}-sb"

export GHEC_SUFFIX


# If you define an ENV variable that has an .env file in it,
# source it and export all the variables in it.
if [[ -n "${ENV:-}" ]]; then
    if [[ -f "${ENV:-}" ]]; then
        set -o allexport
        #shellcheck disable=SC1090
        source "$ENV"
        set +o allexport
    else
        echo "ERROR: Please set up an .env file as directed in sample-env to continue."
        exit 2
    fi
fi

function log_ts {
    date '+[%Y-%m-%d %T]'
}

function iso8601_ts {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

function iso8601_win_safe_ts {
    date -u +"%Y%m%dT%H%M%SZ"
}


# Quick and dirty shell logging system that works
# in a similar way to the GitHub CLI
if "${DEBUG:-false}"; then
    export LOG_LEVEL="DEBUG"
else
    export LOG_LEVEL=${LOG_LEVEL:-INFO}
fi
function log {
    local level
    local message
    level=$1
    shift
    message=$*
    declare -rA LOG_LEVELS=(["DEBUG"]=1 ["INFO"]=2 ["WARN"]=4 ["CRITICAL"]=8 ["ERROR"]=16)
    if [[ ${LOG_LEVELS[$level]} -ge ${LOG_LEVELS[$LOG_LEVEL]} ]]; then
        echo "$(log_ts) [$level] $message"
    fi
}

# This uses bash 4 constructs such as associative arrays. Check that we are running bash 4+.
# MacOS ships with bash 3.x as of 2023 still, ugh.
#
# Ensure we are using a modern bash before proceeding.
# Thanks https://unix.stackexchange.com/a/573828
function assertModernBash() {
    if ! ((BASH_VERSINFO[0] >= 4)); then
        echo "$(ts) [ERROR] bash version ${BASH_VERSINFO[0]} detected, but bash 4+ is required here."
        if [[ "$(uname)" == "Darwin" ]]; then
            echo "$(ts) [INFO] On MacOS, use bash version 5+ from Homebrew."
            echo "$(ts) [INFO] Do 'brew install bash && rehash' and try again."
        fi
        exit 1
    fi
}

function assertGhCliInstalled()
{
    # Check to see if the GitHub CLI is installed
    if [[ -z "$(which gh)" ]]; then
        log ERROR "No installation of the GitHub CLI found. See https://github.com/cli/cli#installation"
        exit 1
    fi
}

function assertJqInstalled() {
    # Check to see if jq is installed
    if [[ -z "$(which jq)" ]]; then
        log ERROR "No installation of jq found."
        exit 1
    fi
}

function assertParallelInstalled() {
    # Check to see if parallel is installed
    if [[ -z "$(which parallel)" ]]; then
        log ERROR "No installation of parallel found."
        exit 1
    fi
}

function getTargetOrg {
    local ghSourceOrg
    ghSourceOrg=${1?You must specify a source organization}
    if [[ -z "$GH_ORG" ]]; then
        echo "${GHEC_PREFIX}-$ghSourceOrg"
    else
        echo "$GH_ORG"
    fi
}

function setCrontab() {
    local CRON_SCRIPT
    local newCrontabLine
    local oldCrontab
    CRON_SCRIPT=${1:?You must specify a CRON script}
    removeCrontab "$CRON_SCRIPT"
    newCrontabLine="0 * * * * $CRON_SCRIPT $$"
    oldCrontab=$(crontab -l)
    if [[ -z "$oldCrontab" ]]; then
        echo "$newCrontabLine" | crontab
    else
       sed "a0 * * * * $CRON_SCRIPT $$" \
            <<<"$oldCrontab" \
            | crontab
    fi
}

function removeCrontab() {
    local CRON_SCRIPT
    CRON_SCRIPT=${1:?You must specify a CRON script}
    crontab -l \
        | (grep -v "$CRON_SCRIPT $$" || true ) \
        | crontab
}

function ghRateRemaining {
    instance=${1:-$GH_SOURCE_HOST}
    gh api \
        --hostname "$instance" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -q '.rate.remaining' \
        rate_limit
}


function rateLimitSleep {
    local remaining
    local sleepTime
    local THRESHOLD
    instance=${1:-$GH_SOURCE_HOST}
    THRESHOLD=${2:-60}
    remaining=$(ghRateRemaining "$instance")
    if [[ $remaining -lt $THRESHOLD ]]; then
        sleepTime=$(((THRESHOLD - remaining) ** 2))
        log DEBUG "Remaining ratelimit $remaining is less than $THRESHOLD, sleeping $sleepTime seconds"
        sleep $sleepTime
    else
        log DEBUG "Remaining ratelimit $remaining is at least $THRESHOLD, no sleep required"
    fi
}


function renewSelfVaultToken() {
    local new_vault_token
    if new_vault_token=$(VAULT_TOKEN="$VAULT_TOKEN" "$SCRIPTS_DIR/renewSelfVaultToken.sh"); then
        VAULT_TOKEN=$new_vault_token
        export VAULT_TOKEN
        log INFO "$0 - Vault token VAULT_TOKEN in $ENV renewed for $(id -un)"
    else
        log ERROR "Renewing vault token from VAULT_TOKEN failed, it is likely stale."
        return 1
    fi
}

function updateVaultTokenEnv() {
    sed -i.bak "s/^VAULT_TOKEN=.*/VAULT_TOKEN=$VAULT_TOKEN/" "$ENV" \
        && rm "$ENV".bak
}

function promptForVaultTokenIfExpired() {
    local tries=10
    local try=0
    local new_vault_token
    log INFO "Checking if Vault token VAULT_TOKEN is valid..."
    if renewSelfVaultToken; then
        log INFO "Vault token is OK, continuing"
        return 0
    fi
    log WARN "VAULT_TOKEN is invalid, attempting $tries tries for getting a fresh token..."
    while [[ "$try" -lt "$tries" ]]; do
        (( try++ )) || true
        log INFO "Enter new vault token, or press the Enter key to re-read the .env file"
        echo -n " 🔐 (attempt $try of $tries) > "
        read -r -s new_vault_token < /dev/tty
        echo ''
        export VAULT_TOKEN=$new_vault_token
        if renewSelfVaultToken; then
            log INFO "Vault token from user input was good - continuing"
            updateVaultTokenEnv
            return 0
        else
            log WARN "No valid vault token found in input, re-reading the .env file"
            # shellcheck disable=SC1090
            source "$ENV"
            if renewSelfVaultToken; then
                log INFO "Vault token from .env was good - continuing"
                return 0
            fi
        fi
    done
    log ERROR "Failed to get an updated vault token"
    return 1
}

function assertInVirtualenv() {
    if ! (cd "$SCRIPTS_DIR"; ./in_virtualenv.py); then
        log ERROR "No python virtual environment detected"
        return 1
    fi
    return 0
}

function assertOrganizationOwner() {
    local token="$1"
    local organization="$2"
    local apiurl="${3:-https://api.github.com}"

    # Get the username associated with the token
    username=$(curl -s -H "Authorization: token $token" "$apiurl/user" | jq -r '.login')

    # Check if the role is admin
    role=$(curl -s -H "Authorization: token $token" "$apiurl/orgs/$organization/memberships/$username" | jq -r '.role')
    echo "role='$role'"
    if [[ "$role" = "admin" ]]; then
       return
    else
       log ERROR "User $username is not an owner of the organization $organization. Please grant necessary permissions to the user and try again"
	   exit 1
    fi
}

function useSystemCAForPython() {
    # If we are running on a Debian derivative, use the system CA bundle for Python scripts using requests
    # Thanks https://stackoverflow.com/a/67601695
    if [[ -f /etc/ssl/certs/ca-certificates.crt ]]; then
        REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
        export REQUESTS_CA_BUNDLE
    fi
}

function archive_repo() {
    local should_archive=${1:-true}
    local instance=${2:-$GH_SOURCE_HOST}
    local sourceOrg=${3:-$ghSourceOrg}
    local repo=${4:-$repo}
    local repoUrl="https://$instance/$sourceOrg/$repo"
    if [[ "$GH_ORG" = "$GHEC_SANDBOX_ORG"  ]]; then
        log INFO "Skipping source repo archiving for $sourceOrg/$repo since destination is ${GHEC_SANDBOX_ORG}"
        return
    fi
    if "$SKIP_ARCHIVE"; then
        log INFO "Skipping source repo archiving for $sourceOrg/$repo since SKIP_ARCHIVE is true"
        return
    fi
    if [ "$should_archive" = "true" ]; then
        log INFO "Archiving repo $repoUrl"
        gh repo archive "$repoUrl" -y
    elif [ "$should_archive" = "false" ]; then
        log INFO "Unarchiving repo $repoUrl"
        gh repo unarchive "$repoUrl" -y
    else
        log WARN "No archiving action carried out for $repoUrl, specify true or false as parameter"
    fi
}


function replace_topics () {
    local repo="$1"
    local updated_topics="$2"
    local org="${3:-$ghSourceOrg}"
    local api_url="${4:-$GHES_API_URL}"
    local pat="${5:-$GH_SOURCE_PAT}"

    curl -L \
        -s \
        -X PUT \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer $pat" \
        "$api_url/repos/$org/$repo/topics" \
        -d "$updated_topics"
}

function check_and_replace_topic() {
    local newTopic="$1"
    local pre_migration="${2:-"false"}"
    local repo="${3:-$repo}"
    local sourceOrg="${4:-$ghSourceOrg}"
    local instance=${5:-$GH_SOURCE_HOST}
    local targetOrg
    targetOrg="$(getTargetOrg "$sourceOrg")"
    if [[ "$GH_ORG" = "${GHEC_SANDBOX_ORG}"  ]]; then
        log INFO "Skipping topic manipulation for $sourceOrg/$repo since destination is ${GHEC_SANDBOX_ORG}"
        return
    fi
    # Get current topics of the repository
    log INFO "Getting all topics on host $instance in /repos/$sourceOrg/$repo/topics"
    topics=$(gh api \
        --hostname "$instance" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "/repos/$sourceOrg/$repo/topics")
    updated_topics=$(jq --arg newstring "$newTopic" '.names += [$newstring]' <<<"$topics")
    existingTopic=$(jq -r '.names[] | select(test("github-cloud-migrating"))' <<<"$topics")
    if [ "$pre_migration" = "true" ]; then
        if [  -n "$existingTopic" ]; then
            log INFO "Topic '$existingTopic' already exists in repo: $repo"
        else
            log INFO "Adding topic '$newTopic' to repo: $repo"
            replace_topics "$repo" "$updated_topics"
        fi
    else
        # Check if a topic  with "github-migrating" or "github-cloud-migrating-archive" exists
        existingTopicArchive=$(jq -r '.names[] | select(. | startswith("github-cloud-migrat")) | select(. | endswith("archive"))' <<<"$topics")
        existingTopicNonArchive=$(jq -r '.names[] | select(. | startswith("github-cloud-migrat"))' <<<"$topics")
        if [ -n "$existingTopicNonArchive" ]; then
            # Replace all topics matching "github-cloud-migrating" with "github-cloud-migrated"
            if [ "$existingTopicNonArchive" != "github-cloud-migrated" ]; then
                updated_topics_non_archive=$(jq --arg v "$existingTopicNonArchive" '.names |= map(gsub($v; "github-cloud-migrated"))' <<<"$topics")
                # Update repository topics
                log INFO "Replacing $existingTopicNonArchive with 'github-cloud-migrated' in $repo"
                replace_topics "$repo" "$updated_topics_non_archive"
                replace_topics "$repo" "$updated_topics_non_archive" "$targetOrg" "$GHEC_API_URL" "$GH_PAT"
            fi

        elif [ -n "$existingTopicArchive" ]; then
            if [ "$existingTopicArchive" != "github-cloud-migrated-archive" ]; then
                # Replace all topics matching "github-cloud-migrating-archive" with "github-cloud-migrated-archive"
                updated_topics_archive=$(jq --arg v "$existingTopicArchive" '.names |= map(gsub($v; "github-cloud-migrated-archive"))' <<<"$topics")
                # Update repository topics
                log INFO "Replacing $updated_topics_archive with 'github-cloud-migrated-archive' in $repo"
                replace_topics "$repo" "$updated_topics_archive"
                replace_topics "$repo" "$updated_topics_archive" "$targetOrg" "$GHEC_API_URL" "$GH_PAT"
            fi

        else
            log INFO "No topic matching 'github-cloud-migrating-archive' or 'github-cloud-migrating' found in $repo, adding topic $newTopic"
            replace_topics "$repo" "$updated_topics"
            replace_topics "$repo" "$updated_topics" "$targetOrg" "$GHEC_API_URL" "$GH_PAT"
        fi
    fi
}

function call_post_migration_scripts() {
    local REPO_MAP_FILE
    REPO_MAP_FILE=${1?You must specify a file with a map of repos with format "ghes-org/ghes-repo,ghec-org/ghec-repo"}
    local repoList=()
    while IFS= read -r line && [[ -n "$line" ]]  ; do
        # Ignore comment lines
        if grep '^#' <<<"$line"; then
            log DEBUG "Ignoring comment $line"
            continue
        fi
        repoList+=("$line")
    done <"$REPO_MAP_FILE"

    log INFO "Updating description of migrated repo"
    "$UPDATE_REPO_DESC" <"$REPO_MAP_FILE"

    log INFO "Patching Buildkite repo"
    "$PATCH_BUILDKITE_PIPELINE" <"$REPO_MAP_FILE"

    log INFO "Migrate and activate webhooks"
    "$MIGRATE_WEBHOOK" <"$REPO_MAP_FILE"

    log INFO "Migrate repo permissions for user and teams"
    "$MIGRATE_PERMISSIONS" <"$REPO_MAP_FILE"

    log INFO "Migrate Gator Pull Requests (undraft, remove POC)"
    "$MIGRATE_GATOR_PULL_REQUESTS" <"$REPO_MAP_FILE"

    log INFO "Migrate Repo permission to Apps"
    "$MIGRATE_APP_REPO_PERMISSION" <"$REPO_MAP_FILE"

    log INFO "Migrate Github Pages"
    "$MIGRATE_GH_PAGES" <"$REPO_MAP_FILE"

    log INFO "Migrating LFS objects in migrated repos"
    for line in "${repoList[@]}"; do
        sourcerepo="$(cut -d, -f1 <<<"$line")"
        if grep -Fxq "$sourcerepo" "$LFS_FILE"
        then
            "$MIGRATE_LFS"<<<"$sourcerepo"
            log INFO "Migrated LFS objects in $sourcerepo"
        else
            log INFO "$sourcerepo not an LFS activated repo"
        fi
        repo="$(cut -d/ -f2 <<<"$sourcerepo")"
        check_and_replace_topic "github-cloud-migrated" "false" "$repo"

    done
}

