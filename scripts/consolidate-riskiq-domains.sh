#!/usr/bin/env bash
# consolidate-riskiq-domains.sh
#
# Consolidate riskiq domains

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
DATA_DIR="$BASE_DIR/data/riskiq"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

cat "$DATA_DIR"/example.com"${GHEC_PREFIX}"*.csv \
	| grep -v hostname \
	| cut -d, -f1 \
	| sort -u \
	| "$SCRIPTS_DIR/domain-sort.py" \
	> "$DATA_DIR/riskiq-exposed-domains.txt"
