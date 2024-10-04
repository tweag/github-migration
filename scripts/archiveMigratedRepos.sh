#!/usr/bin/env bash
# archiveMigratedRepos.sh
#
# Given a list of organization/repository pairs from GitHub Enterprise Server,
# this script will archive the corresponding repositories on GitHub Enterprise Cloud.
#
# Usage:
#    scripts/archiveMigratedRepos.sh < data/repoList.txt

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
DATA_DIR="$DIR/../data"
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR DATA_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

################## Required Environment Variables ####################
# export GH_PAT=<The Personal Access Token from GHEC>
################## Optional Environment Variables ####################
# export GH_ORG=<GHEC destination org for the repos to be migrated>

unset GH_TOKEN # Ditch this one as it interferes with using gh cli in subtle ways

GH_PAT=${GH_PAT:?You must specify a Personal Access Token from GHEC in the GH_PAT environment variable}
GH_ORG=${GH_ORG:-}

assertModernBash
assertGhCliInstalled

log INFO "$0 - archive migrate repositories"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

inputLines=()


gh auth login \
    --hostname github.com \
    --with-token \
    <<< "$GH_PAT"

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
    log ERROR "No repositories found to archive, please pass org/repo pairs in STDIN"
    log INFO "Usage: ./scripts/archiveMigratedRepos.sh < data/repoList.txt"
    exit 1
fi
if [[ "$GH_ORG" = "${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}"  ]]; then
    matchingRepo=$(printf "%s\n" "${inputLines[@]}" | sed 's#.*/##' | sort | uniq -d)
    set +e
    result=$(printf "%s\n" "${inputLines[@]}" | grep -E "/${matchingRepo}"'$')
    set -e
    if [ -z "$result" ]; then
        # shellcheck disable=SC2207
        UNIQ_REPOS=($(printf "%s\n" "${inputLines[@]}" | sort -u))
    else
        log ERROR "Repo duplicated in input: $(tr "\n" " " <<<"$result")"
        exit 1
    fi
else
    # shellcheck disable=SC2207
    UNIQ_REPOS=($(printf "%s\n" "${inputLines[@]}" | sort -u))
fi

for line in "${UNIQ_REPOS[@]}"; do
    ghSourceOrg=$(cut -d/ -f1 <<<"$line")
    ghTargetOrg="$(getTargetOrg "$ghSourceOrg")"
    repo=$(cut -d/ -f2 <<<"$line")
    ghTargetUrl="https://github.com/$ghTargetOrg/$repo"
    log INFO "Archiving $ghTargetUrl"
    gh repo archive -y "$ghTargetOrg/$repo"
    rateLimitSleep github.com
done
