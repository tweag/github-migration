#!/usr/bin/env bash
# gitPushStepwise.sh
#
# Implement the stepwise push outlined in:
#   https://docs.github.com/en/get-started/using-git/troubleshooting-the-2-gb-push-limit
#
# Requires that the bare git repo that
#
# Usage:
#    scripts/gitPushStepwise.sh

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
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

BRANCH_NAME=${1:-master}
REMOTE_NAME=${2:-github}
STEP_SIZE=${3:-1000}

export BRANCH_NAME

step_commits=$(git log --oneline --reverse "refs/heads/$BRANCH_NAME" | awk "NR % $STEP_SIZE == 0")
log INFO "step commits: $step_commits"
#shellcheck disable=SC2162,SC2141
echo "$step_commits" | while IFS=" \n\t" read commit message; do
	log INFO "commit: $commit"
	log INFO "message: $message"
	log INFO "Pushing $commit to $BRANCH_NAME"
	git push "$REMOTE_NAME" "$commit:refs/heads/$BRANCH_NAME"
done
