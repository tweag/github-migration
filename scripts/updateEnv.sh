#!/usr/bin/env bash
# updateEnv.sh
#
# Update the environment file locally with tokens that have to be renewed
#
# This initially is useful for updating the Vault token in one command.
#
# Usage:
#    scripts/updateEnv.sh

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
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR

# shellcheck disable=SC1091
source "$SCRIPTS_DIR/common.sh"

VAULT_TOKEN=$("$SCRIPTS_DIR/getVaultToken.sh")
updateVaultTokenEnv
export VAULT_TOKEN
