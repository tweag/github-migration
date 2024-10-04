#!/usr/bin/env bash
# getSourcegraphMatches.sh
#
# Retrieve all matches for github.example.com from Sourcegraph
#
# Requires Sourcegraph CLI, install on Mac via Homebrew with:
#
#   brew install sourcegraph/src-cli/src-cli


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

CALL_APIS=${1:-true}

if "$CALL_APIS"; then
  export SRC_ACCESS_TOKEN=${SRC_ACCESS_TOKEN:?You must specify a SRC_ACCESS_TOKEN environment variable}
fi

export SRC_ENDPOINT="https://sourcegraph.example.com/"
RAW_RESULTS="$DATA_DIR/sourcegraph-github.example.com.json"
UNIQUE_FILES="$DATA_DIR/sourcegraph-github.example.com-unique_file_names.txt"
UNIQUE_GLOBS="$DATA_DIR/sourcegraph-github.example.com-unique-globs.yml"

if $CALL_APIS; then
	src search -json \
		'github.example.com select:content count:all' \
		> "$RAW_RESULTS"
fi

jq  '.Results[].file.name' "$RAW_RESULTS" \
	| cut -d\" -f 2 \
	| sort -u \
	> "$UNIQUE_FILES"

echo '          paths:' > "$UNIQUE_GLOBS"

# Get file globs for extensions
grep \\. "$UNIQUE_FILES" \
	|  sed -e '
		s/^.*\.\([^.]*\)$/\1/;
		s/\(.*\)/          - "**\/*.\1"/'  \
	| sort -u \
	>> "$UNIQUE_GLOBS"

# Get file globs for files without extensions
grep -v \\. "$UNIQUE_FILES" \
	| sort -u \
	|  sed -e '
		s/\(.*\)/          - "**\/\1"/'  \
	>> "$UNIQUE_GLOBS"

