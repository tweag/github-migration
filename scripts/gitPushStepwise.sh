#!/usr/bin/env bash
# gitPushStepwise.sh
#
# Implement the stepwise push outlined in:
#   https://docs.github.com/en/get-started/using-git/troubleshooting-the-2-gb-push-limit
#
# Requires a git repo checked out to the branch you want to push. Usually you should start
# with the default branch. Once that is pushed, it should be easy to check out other branches
# you want to keep and push those, with or without the stepwise push script. Then you can push
# the tags and you will have a complete copy of the git repository.
#
# This approach may not work well on some repositories, if it fails you could instead try the
# chunked-push.sh script outlined in this gist:
#
#   https://gist.github.com/robandpdx/86831d48ab7312f844a9e4ec2348b30a#file-chunked-push-sh
#
# Usage:
#    scripts/gitPushStepwise.sh [branch_name] [remote_name] [step_size]

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
log DEBUG "step commits: $step_commits"
#shellcheck disable=SC2162,SC2141
echo "$step_commits" | while IFS=" \n\t" read commit message; do
	log INFO "commit: $commit"
	log INFO "message: $message"
	log INFO "Pushing $commit to $BRANCH_NAME"
	git push --force --no-follow-tags "$REMOTE_NAME" "$commit:refs/heads/$BRANCH_NAME"
done
