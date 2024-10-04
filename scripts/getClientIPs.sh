#!/usr/bin/env bash
# getClientIps.sh
#
# Take extracts from Kibana dashboard reports and create a
# unique list of client IPs

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
DATA_DIR="$DIR/../data/GHCM-103_ghes-client-ips"
export BASE_DIR SCRIPTS_DIR

cat "$DATA_DIR/"*.csv \
    | cut -d\" -f2 \
    | grep '^[0-2]' \
    | grep -v , \
    | sort -u  \
    | grep -v 127\.0\.0\.1 \
    > "$DATA_DIR/GHCM-103-client-ips.txt"
