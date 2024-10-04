#!/usr/bin/env bash
# findStragglerRepos.sh
#
# Create audit script to find straggler repositories that have not been migrated yet
#
# Instructions:
#
# Copy the repository slugs from the migration tracking spreadsheet
# into the data/repos_from_sheet.txt file, then run this script.
#
# See this file for output: data/repos_not_in_sheet.txt

set -euo pipefail

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
DEBUG=${DEBUG:-false}
$DEBUG && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DATA_DIR="$DIR/../data"

# shellcheck disable=SC1091
source "$DIR/common.sh"

assertModernBash

INPUT_FILE_ACTIVE="$DATA_DIR/repos_active.txt"
INPUT_FILE_SHEET="$DATA_DIR/repos_from_sheet.txt"
OUTPUT_FILE="$DATA_DIR/repos_not_in_sheet.txt"

# Check if both files exist
# repos_active.txt comes from output of running the script getAllData.sh
# repos_from_sheet comes from our migration ordering spreadsheet.
if [ ! -f "$INPUT_FILE_ACTIVE" ] || [ ! -f "$INPUT_FILE_SHEET" ]; then
    log ERROR "One or both of the required files does not exist."
    exit 1
fi

# Read the complete repo list into an array
mapfile -t complete_repos < "$INPUT_FILE_ACTIVE"

# Read the extracted repo list into an array
mapfile -t extracted_repos < "$INPUT_FILE_SHEET"

# Create associative arrays for easy lookup
declare -A extracted_repo_map


for repo in "${extracted_repos[@]}"; do
    extracted_repo_map["${repo:-}"]=1
done

# Output file
cat < /dev/null > "$OUTPUT_FILE"

# Find repos in complete list that are not in the extracted list
log INFO "Repos in complete list but not in extracted list:"
set +u
for repo in "${complete_repos[@]}"; do
    if [ ! "${extracted_repo_map[$repo]}" ]; then
        echo "$repo" >> "$OUTPUT_FILE"
    fi
done
set +u

log INFO "Missing repos outputted to $OUTPUT_FILE"
