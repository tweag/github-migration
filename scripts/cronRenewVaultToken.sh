#!/usr/bin/env bash
# cronRenewVaultToken.sh
#
# Renew the vault token in an .env file periodically, from cron
#
# Usage:
#
#    echo "0 * * * * $HOME/Documents/github-migration/scripts/cronRenewVaultToken.sh' | crontab

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

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

VAULT_TOKEN=${VAULT_TOKEN:?You must specify a Vault token in the VAULT_TOKEN environment variable.}

PARENT_PID=${1:?You must specify the PID of the migration script that runs this: Use \$\$}

# Thanks https://unix.stackexchange.com/a/61936
exec > >(logger) 2>&1

# Extra safeguard: only keep running this if a migration script is running
if ps "$PARENT_PID" > /dev/null 2>&1; then
    logger INFO "Process with PID $PARENT_PID detected, renewing Vault token"
    renewSelfVaultToken
else
    logger WARN "No process with PID $PARENT_PID detected, skipping Vault token renewal"
fi

