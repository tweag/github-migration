#!/usr/bin/env bash
# getSourcegraphQuerySlugs.sh
#
# Retrieve org/repo slugs for matches to a Sourcegraph query
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

QUERY=${1:?You must specify a Sourcegraph query as a parameter}
CALL_APIS=${2:-true}

if "$CALL_APIS"; then
    export SRC_ACCESS_TOKEN=${SRC_ACCESS_TOKEN:?You must specify a SRC_ACCESS_TOKEN environment variable}
fi

export SRC_ENDPOINT="https://sourcegraph.example.com"

# Create a temp file and force remove it at exit
scratch=$(mktemp -t migrate.XXXXXXXXXX)
function finish {
    rm -rf "$scratch"
}
trap finish EXIT



if $CALL_APIS; then
    src search -json \
        "$QUERY" \
        > "$scratch"
fi

jq -r '.Results[].repository.url' "$scratch" \
    | cut -d/ -f 3,4 \
    | sort -u

# This was the inspiration for this
# set -o allexport && source .env && set +o allexport
# mkdir -p data/ && src search --json '"file:^.buildkite/.* repo:^github.example.com/.* count:all"' | tee data/buildkite.json
# mkdir -p data && src search --json 'file:^.buildkite/.* repo:^github.example.com/org1/[0-9][A-Za-m].* count:all' | tee data/buildkite-1.json
# mkdir -p data && src search --json 'file:^.buildkite/.* repo:^github.example.com/org1/[m-z].* count:all' | tee data/buildkite-2.json
# mkdir -p data && src search --json 'file:^.buildkite/.* repo:^github.example.com/org1/[r-z].* count:all' | tee data/buildkite-3.json
