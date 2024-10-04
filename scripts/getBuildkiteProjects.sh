#!/usr/bin/env bash
# getBuildkiteProjects.sh
#
# Retrieve all the buildkite projects.
#
# Usage:
#    getBuildkiteProjects.sh

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
DATA_DIR="$DIR/../data/buildkite-projects"
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

assertJqInstalled

BUILDKITE_TOKEN=${BUILDKITE_TOKEN:?You must have a BUILDKITE_TOKEN environment variable}
BUILDKITE_ORG=example

mkdir -p "$DATA_DIR"

page=1
curl \
    --location "https://api.buildkite.com/v2/organizations/$BUILDKITE_ORG/pipelines" \
    --header "Authorization: Bearer $BUILDKITE_TOKEN" \
    -s -v \
    2>/tmp/headers \
    >/dev/null
lastpage=$(grep link /tmp/headers | cut -d\? -f 3,4 | cut -d\> -f 1 | cut -d= -f2)
for page in $(seq 1 "$lastpage"); do
    $DEBUG && echo "Getting page $page"
    curl --location "https://api.buildkite.com/v2/organizations/$BUILDKITE_ORG/pipelines" --header "Authorization: Bearer $BUILDKITE_TOKEN" \
      -s  \
      > "$DATA_DIR/buildkite_pipelines-$page.json"
done
jq -n '[inputs | add]' "$DATA_DIR/buildkite_pipelines-*.json" \
    > "$DATA_DIR/buildkite_pipelines.json"
# TODO: analyze this to find pipelines that have repo names and pipeline names mismatched
# Maybe emit a CSV file with jq that we can load?
# Or a different JSON file with a map of repo slugs to names when they don't match?
