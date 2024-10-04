#!/usr/bin/env bash
# getVaultToken.sh
#
# Get a Vault token using the Wayfair-enhanced CLI
#
# Requires the special Wayfair vault client CLI and jq
#
# Useful for retrieving a user-level Vault token for testing.
# usage:
#     export VAULT_TOKEN=$(scripts/getVaultToken.sh)
 
# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
${DEBUG:-false} && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

unset VAULT_TOKEN
export VAULT_TOKEN
vault token create
