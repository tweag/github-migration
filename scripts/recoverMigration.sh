#!/usr/bin/env bash
# recoverMigration.sh
#
# Given a webhook map file, run the last steps of a migration
# Running this is a better alternative than running the unarchive and decoupled migrate scripts.
# Usage:
#    scripts/decoupledMigrate.sh data/migrations/webhokMapFile-20240301000000.txt

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

assertModernBash
assertJqInstalled
assertParallelInstalled
assertInVirtualenv
useSystemCAForPython

function finish {
    removeCrontab "$CRON_RENEW_VAULT_TOKEN"
}
trap finish EXIT

WEBHOOK_MAP_FILE=${1:?You must specify a webhook map file as a command line parameter}

if [[ ! -f "$WEBHOOK_MAP_FILE" ]]; then
    log ERROR "$WEBHOOK_MAP_FILE does not exist."
    exit 1
fi
# Thanks https://superuser.com/a/1508996
WEBHOOK_MAP_FILE="$(cd "$(dirname "$1")"; pwd -P)/$(basename "$1")"

logger DEBUG "Canonicalized WEBHOOK_MAP_FILE=$WEBHOOK_MAP_FILE"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"


promptForVaultTokenIfExpired

setCrontab "$CRON_RENEW_VAULT_TOKEN"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

gh auth login \
    --hostname "$GH_SOURCE_HOST" \
    --with-token \
    <<< "$GH_SOURCE_PAT"
gh auth login \
    --hostname github.com \
    --with-token \
    <<< "$GH_PAT"


call_post_migration_scripts "$WEBHOOK_MAP_FILE"
