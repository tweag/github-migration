#!/usr/bin/env bash
# vaultTokenLookupSelf.sh
#
# Looks up a Vault token, returns JSON for token details.
#
# usage:
#     export VAULT_TOKEN=$(scripts/vaultTokenLookupSelf.sh)

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
${DEBUG:-false} && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

VAULT_URI="https://vault.example.com:8200/v1/auth/token/lookup-self"
curl \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    --request GET \
    "$VAULT_URI" \
    --fail \
    --silent
