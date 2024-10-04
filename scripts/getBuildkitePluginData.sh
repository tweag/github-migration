#!/usr/bin/env bash
# getBuildkitePluginData.sh
#
# Ensure we have a good list of repos for Buildkite plugin migration
#
# Copy the Gator-repo-expr-cut-n-paste column from: DOCUMENT_URL
# into plugins-sheet-source.yml
#
 

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
DATA_DIR="$DIR/../data/buildkite-plugins"
export BASE_DIR


grep -v '^$' "$DATA_DIR/plugins-sheet-source.yml" \
	> "$DATA_DIR/plugins-sheet-source-trimmed.yml"

grep -v '^Gator-repo-expr' "$DATA_DIR/plugins-sheet-source-trimmed.yml" \
	| sed 's/^        - //' \
	| sort \
	> "$DATA_DIR/plugins-sheet-source-sorted.txt"
 
sort -u \
	< "$DATA_DIR/plugins-sheet-source-sorted.txt" \
	> "$DATA_DIR/plugins-sheet-source-unique.txt"

if ! diff \
	"$DATA_DIR/plugins-sheet-source-sorted.txt" \
	"$DATA_DIR/plugins-sheet-source-unique.txt" 
then
	echo "Duplicate entries extracted from spreadsheet found, aborting."
	exit 1
fi 
