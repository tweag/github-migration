#!/usr/bin/env bash
# getSourcegraphSlugs-example.sh
#
# Via Sourcegraph queries, find repo slugs needed for an example issue
#
# Emit repo slugs
#
# Usage:
#    scripts/getSourcegraphSlugs-example.sh

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
DATA_DIR="$DIR/../data/example"
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

function emit_munged_queries() {
    local query
    query=${1:?Speficy a Sourcegraph query with ~~~ where [0-9A-Za-z] must get substituted}
    for x in 0 1 2 3 4 5 6 7 8 9 a b c d e f g h i j k l m n o p q r s t u v w x y z; do
        echo "${query//~~~/$x}"
    done
}

function get_slug_from_query() {
    while read -r line; do
        log DEBUG "$line"
        "$SCRIPTS_DIR/getSourcegraphQuerySlugs.sh" "$line"
    done
}

mkdir -p "$DATA_DIR"

emit_munged_queries  \
    'repo:^github.example.com/org1/~~~.* content:github.example.com/org1/a-particular-example-repo language:YAML count:all' \
    | get_slug_from_query \
    > "$DATA_DIR/example.txt"

sed 's/^/        - /' < "$DATA_DIR/example.txt" > "$DATA_DIR/example.yaml"
