#!/usr/bin/env bash
# reclaimAllMannequins.sh
#
# Reclaim all the mannequins for the target github.com organizations.
#
# Usage:
#    scripts/reclaimAllMannequins.sh

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
export BASE_DIR SCRIPTS_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

RECLAIM_MANNEQUINS="$SCRIPTS_DIR/reclaimMannequins.sh"

GH_PAT=${GH_PAT:?You must have GH_PAT set in your environment to proceed. See directions in env-sample}

ORGS='example-sb
example-org1
example-org2'

for org in $ORGS; do
    log INFO "Reclaiming mannequins for $org"
    GH_TOKEN="$GH_PAT" "$RECLAIM_MANNEQUINS" "$org"
done
