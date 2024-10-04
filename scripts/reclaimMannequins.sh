#!/usr/bin/env bash
# reclaimMannequins.sh
#
# Reclaim mannequins for a GitHub organization.
#
# Prone to being rate-limited, try to use this internally with CSV batches that are no larger than 2500 lines each and
# check for adequate quota on github.com for your personal access token before each run.
#

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
${DEBUG:-false} && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

# Credit to http://stackoverflow.com/a/246128/424301
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$DIR/.."
SCRIPTS_DIR="$BASE_DIR/scripts"

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

# Create a temp dir and force remove it at exit
TMP_DIR=$(mktemp -dt reclaimMannequins.XXXXX)
function finish {
    rm -rf "$TMP_DIR"
}
trap finish EXIT


ghTargetOrg=${1:?You must specify a GitHub organization to run this script.}
batchSize=${2:-100}
((sleepLimit=batchSize * 2))
mannequin_file="mannequin-$ghTargetOrg-$(iso8601_win_safe_ts).csv"

log INFO "Generating mannequins for $ghTargetOrg - creating $mannequin_file"
cd "$TMP_DIR"
rateLimitSleep github.com
gh gei generate-mannequin-csv --github-target-org "$ghTargetOrg" --output "$mannequin_file"

sed -e "
    1!s/\([^,]*\),\([^,]*\),/\1,\2,\1_$USER_SUFFIX/
    /^sa-aap-github/d
    " "$mannequin_file" > "${mannequin_file}.tmp"
mv "${mannequin_file}.tmp" "$mannequin_file"
# divide file into chunks of $batchSize entries
parallel --header : --pipe "-N${batchSize}" "cat >mannequin-parallel_{#}.csv" < "$mannequin_file"

for i in mannequin-parallel_*; do
    if [[ -f "$i" ]]; then
        log INFO "Reclaiming mannequins for $ghTargetOrg - using $i"
        counter=1
        while [[ $counter -le 5 ]]; do
            rateLimitSleep github.com "$sleepLimit"
            gh gei reclaim-mannequin --skip-invitation --github-target-org "$ghTargetOrg" --csv "$i" --no-prompt && break
            ((counter++))
        done
    else
        log INFO "No mannequins to reclaim in $ghTargetOrg"
    fi
done
cd - > /dev/null 2>&1
