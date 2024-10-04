#!/usr/bin/env bash
# fmt.sh
#
# Run all formatters

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
DATA_DIR="$DIR/../data/migrations"
ENV="$BASE_DIR/.env"
export BASE_DIR SCRIPTS_DIR DATA_DIR

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

log "INFO" "*** Running isort"
isort "$SCRIPTS_DIR/"
log "INFO" "*** Running black"
black "$SCRIPTS_DIR/"
if which shellcheck; then
    log INFO "*** Running shellcheck"
    shellcheck -f diff "$SCRIPTS_DIR/"*.sh | patch -p0
else
    log WARN "*** Shellcheck (optional) not found"
fi
