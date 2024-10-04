#!/usr/bin/env bash
# getMigrationIpAllowlist.sh
#
# Get the IPs needed for the migration environment allowlist

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
${DEBUG:-false} && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

# Credit to http://stackoverflow.com/a/246128/424301
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$DIR/.."
SCRIPTS_DIR="$BASE_DIR/scripts"
DATA_DIR="$DIR/../data"
export BASE_DIR SCRIPTS_DIR

ALLOWLIST="$DATA_DIR/migration-ip-allowlist.txt"

curl -L \
  -s \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/meta \
  | jq '.web + .api + .git + .enterprise_importer | .[]' \
  | cut -d \" -f 2 \
  | sort -u \
  > "$ALLOWLIST"
