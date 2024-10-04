#!/usr/bin/env bash
# getAllData.sh
#
# Export all GitHub data to files in data subdirectory
#
# The intent here is to be able to run all the scripts that retrieve
# data from GitHub and other sources in one go, after setting all the access
# tokens (see env-sample in the project root).
#
# As new scripts get added to this we can see if they get ref

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
DATA_DIR="$DIR/../data"
ENV="$BASE_DIR/.env"

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

useSystemCAForPython
assertInVirtualenv

export CALL_APIS=${1:-true}

if "$CALL_APIS"; then
  GH_SOURCE_PAT=${GH_SOURCE_PAT:?You must specify a GH_SOURCE_PAT environment variable with a GitHub personal access token.}
  SRC_ACCESS_TOKEN=${SRC_ACCESS_TOKEN:?You must specify a SRC_ACCESS_TOKEN environment variable for Sourcegraph API token.}
fi

# Audit whether we have all the get scripts represented here
cd "$SCRIPTS_DIR"
notfound=false
for script in get*.sh; do
	# This makes sure we did not miss one of these - except for these, which
        # are not actually called from this script, intentionally:
        #  getVaultToken.sh
        #  getTeamName.sh
        #  getWorkgroupName.sh
        #  getSourcegraphQuerySlugs.sh
        #  getSourcegraphQuerySlugs.sh
        #  getSourcegraphSlugs_CLIC-19.sh
        #  getSourcegraphSlugs_GHCM-195.sh
	if ! grep "$script" getAllData.sh > /dev/null 2>&1; then
		echo ERROR: NOT found in getAllData: "$script"
		notfound=true
	fi
done
if $notfound; then
	exit 3
fi

# Prepare to run the data gathering scripts
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"
#
# Get webhooks
if "$CALL_APIS"; then
  for org in $ORGS; do
    GH_ORG="$org" "$SCRIPTS_DIR/getWebhookList.py"
  done
fi
sort -u "$DATA_DIR"/hooksOrgUniquelist_*  \
  | "$SCRIPTS_DIR"/domain-sort.py \
  > "$DATA_DIR/hooks-unique-domain-sorted.txt"
sort -u "$DATA_DIR"/repos_archived_*  \
  > "$DATA_DIR/repos_archived.txt"
sort -u "$DATA_DIR"/repos_active_*  \
  > "$DATA_DIR/repos_active.txt"
sort -u "$DATA_DIR"/repos_archived_*  \
  "$DATA_DIR"/repos_active_*  \
  > "$DATA_DIR/repos_all.txt"


# Get Buildkite projects
## TODO: investigate why this is bombing. Skip for now.
#if "$CALL_APIS"; then
#  "$SCRIPTS_DIR/getBuildkiteProjects.sh"
#fi

# Get mappings of ids to groups
if "$CALL_APIS"; then
  "$SCRIPTS_DIR/getMigrationGroupNames.sh"
fi

# Get client IP matches from Sourcegraph dump
"$SCRIPTS_DIR/getClientIPs.sh"

# Get buildkite plugin data
"$SCRIPTS_DIR/getBuildkitePluginData.sh"


# Consolidate riskiq domains from raw data
"$SCRIPTS_DIR/consolidate-riskiq-domains.sh"


# Get webhooks domain IP map and use it to create vault secrets
if "$CALL_APIS"; then
  "$SCRIPTS_DIR/getWebhookType.py"
  promptForVaultTokenIfExpired
  "$SCRIPTS_DIR/createVaultSecretYaml.py"
fi

# Find domains that are exposed in public DNS and that are safe currently
rm -f "$DATA_DIR/hooks-riskiq-exposed-domains.txt"
while read -r hook; do
  grep ^"$hook"$ "$DATA_DIR/riskiq/riskiq-exposed-domains.txt" \
    >> "$DATA_DIR/hooks-riskiq-exposed-domains.txt" || true
done < "$DATA_DIR/hooks-unique-domain-sorted.txt"
diff "$DATA_DIR/hooks-riskiq-exposed-domains.txt" "$DATA_DIR/hooks-unique-domain-sorted.txt" \
  | grep '^>' \
  | cut -c3- \
  | grep -E '(example.com|example.org)$' \
  > "$DATA_DIR/hooks-riskiq-unexposed-domains.txt" \
  || true

# Get non-LDAP user list
if "$CALL_APIS"; then
  "$SCRIPTS_DIR/getUserList.py"
fi

# Get LDAP and non-LDAP Team list
if "$CALL_APIS"; then
  for org in $ORGS; do
    GH_ORG="$org" "$SCRIPTS_DIR/getTeamList.py"
  done
fi

## These are timing out - and we don't really need this anymore at thi
# stage of the game.
# Get Sourcegraph oddball repos
#if "$CALL_APIS"; then
#  "$SCRIPTS_DIR/getSourcegraphOddballs.sh"
#fi
#
## Get SourceGraph matches
#if "$CALL_APIS"; then
#  "$SCRIPTS_DIR/getSourcegraphMatches.sh"
#fi

cd "$DATA_DIR"
# Get IP allowlist for migration data
"$SCRIPTS_DIR/getMigrationIpAllowlist.sh"
