#!/usr/bin/env bash
# migrateLfs.sh
#
# Given a list of organization/repository pairs, this script will migrate those repositories
# from GitHub Enterprise Server to GitHub Enterprise Cloud.
#
# Usage:
#    scripts/migrate.sh < data/repoList.txt

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
export BASE_DIR SCRIPTS_DIR

GH_PAT=${GH_PAT:?You must specify a Personal Access Token from GHEC in the GH_PAT environment variable}
GH_SOURCE_PAT=${GH_SOURCE_PAT:?You must specify a Personal Access Token from GHES in the GH_SOURCE_PAT environment variable}

GH_ORG=${GH_ORG:-}
#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

# Create a temp dir and force remove it at exit
TMP_DIR=$(mktemp -dt migrateLfs.XXXXXXX)
function finish {
    rm -rf "$TMP_DIR"
}
trap finish EXIT

cd "$TMP_DIR"

inputLines=()
## Read in all the repos from STDIN, and
## validate they are present on the source,
## and skip and warn if they are already present on the destination
while IFS= read -r line && [[ -n "$line" ]]  ; do
    # Ignore comment lines
    if grep '^#' <<<"$line"; then
        log DEBUG "Ignoring comment $line"
        continue
    fi
    inputLines+=("$line")
done


if [[ ${#inputLines[*]} -eq 0 ]]; then
    log ERROR "No repositories requiring LFS migration passed via STDIN, please pass org/repo pairs in STDIN"
    log INFO "Usage: ./scripts/migrateLfs.sh < data/repoList.txt"
    exit 1
fi
# shellcheck disable=SC2207
UNIQ_REPOS=($(printf "%s\n" "${inputLines[@]}" | sort -u))

for line in "${UNIQ_REPOS[@]}"; do
    ghSourceUrl="https://$GH_SOURCE_PAT@github.example.com/$line.git"
    repo=$(cut -d/ -f2 <<<"$line")
    ghSourceOrg=$(cut -d/ -f1 <<<"$line")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    ghTargetUrl="https://$GH_PAT@github.com/$ghTargetOrg/$repo.git"
    log INFO "Cloning repo $line"
    git clone "$ghSourceUrl"

    cd "$repo"
    log INFO "fetching git LFS objects"
    git lfs fetch --all origin
    git remote add githubcloud-origin "$ghTargetUrl"
    log INFO "Pushing LFS objects to new remote"
    git lfs push --all githubcloud-origin
    log INFO "Completed lfs push successfully!!"
    cd "$TMP_DIR"
done
