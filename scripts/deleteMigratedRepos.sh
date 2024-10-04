#!/usr/bin/env bash
# deleteMigratedRepos.sh
#
# Given a list of organization/repository pairs from GitHub Enterprise Server,
# this script will delete the repo counterparts
# in the https://github.com/${GHEC_PREFIX}-${GHEC_SANDBOX_ORG} organization in GitHub Enterprise Cloud.
#
# Usage:
#    scripts/deleteMigratedRepos.sh < data/repoList.txt

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# Create a temp file and force remove it at exit
scratch=$(mktemp -t migrate.XXXXXXXXXX)
function finish {
    rm -rf "$scratch"
}
trap finish EXIT

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

################## Required Environment Variables ####################
# export GH_PAT=<The Personal Access Token from GHEC>
################## Optional Environment Variables ####################
# export GH_ORG=<GHEC destination org for the repos to be migrated>

GH_PAT=${GH_PAT:?You must specify a Personal Access Token from GHEC in the GH_PAT environment variable}
GH_ORG=${GH_ORG:-}

ack=${1:-}

OVERRIDE="be-really-sure-$(date '+%Y-%m-%d')"

assertModernBash
assertGhCliInstalled

log INFO "$0 - deleting rpositories in ${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}"
log DEBUG "OVERRIDE is $OVERRIDE"

if [[ "$GH_ORG" = "${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}" ]]; then
    log INFO "GH_ORG is ${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}, deleting without confirmation"
elif [[ -z "$GH_ORG" ]]; then
    log WARN "GH_ORG is empty, this will delete non-sandbox repos."
    if [[ "$ack" = "$OVERRIDE" ]]; then
        log WARN "Deleting non-sandbox repos."
    else
        log ERROR "To delete repos outside of ${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}, you must specify '$OVERRIDE' as a command line parameter"
        exit 1
    fi
else
    log ERROR "GH_ORG is '$GH_ORG' NOT undefined or ${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}, this is not supported."
    exit 1
fi

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

inputLines=()

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
    log ERROR "No repositories requiring deletion passed via STDIN, please pass org/repo pairs in STDIN"
    log INFO "Usage: ./scripts/deleteMigratedRepos.sh < data/repoList.txt"
    exit 1
fi

# shellcheck disable=SC2207
UNIQ_REPOS=($(printf "%s\n" "${inputLines[@]}" | sort -u))

for line in "${UNIQ_REPOS[@]}"; do
    log INFO "Processing $line"
    ghSourceOrg=$(cut -d/ -f1 <<<"$line")
    repo=$(cut -d/ -f2 <<<"$line")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    ghTargetUrl="https://github.com/$ghTargetOrg/$repo"
    if GH_HOST=github.com gh repo view "$ghTargetUrl" --json name > /dev/null 2>&1; then
        log INFO "Deleting $ghTargetUrl"
        GH_HOST=github.com gh repo delete "$ghTargetUrl" --yes
    else
        log INFO "Repo $ghTargetUrl does not exist - no deletion needed"
    fi
    rateLimitSleep github.com
done
