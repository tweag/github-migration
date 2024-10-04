#!/usr/bin/env bash
# common.sh
#
# Common functions
# Include this from other scripts
#
# Usage:
#    #shellcheck disable=SC1090,SC1091
#    source "$SCRIPTS_DIR/common.sh"
################## Required Environment Variables ####################
# export GH_SOURCE_PAT=<The Personal Access Token from GHES>

GH_SOURCE_PAT=${GH_SOURCE_PAT:?You must specify a Personal Access Token from GHES in the GH_SOURCE_PAT environment variable}
GH_SOURCE_HOST=${GH_SOURCE_HOST:-github.example.com}
GH_ORG=${GH_ORG:-}

# Local SSH connection details
SSH_USER="admin"
SSH_HOST="github.example.com"
SSH_KEY="$HOME/.ssh/id_ed25519-gcp"


# GitHub Enterprise server details
GHE_USER="bob_ross"
GHE_TOKEN=$GH_SOURCE_PAT
SKIP_ARCHIVE=${SKIP_ARCHIVE:-false}

# Directory to store the archive on the remote server
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$DIR/.."
SCRIPTS_DIR="$BASE_DIR/scripts"
DATA_DIR="$DIR/../data/migrations"
LOCAL_ARCHIVE_DIR="$DATA_DIR/archive"

REMOTE_BASE_DIR="/home/admin/$GHE_USER/github-migration"
REMOTE_DATA_DIR="$REMOTE_BASE_DIR/data/migrations"
REMOTE_ARCHIVE_DIR="$REMOTE_DATA_DIR/archive/"
REMOTE_SCRIPT_DIR="$REMOTE_BASE_DIR/scripts/migrateEci.sh"

#shellcheck disable=SC1090,SC1091
source "$SCRIPTS_DIR/common.sh"

gh auth login \
    --hostname "$GH_SOURCE_HOST" \
    --with-token \
    <<< "$GH_SOURCE_PAT"

while IFS= read -r line; do
    # Ignore comment lines
    if grep '^#' > /dev/null 2>&1 <<<"$line"; then
        continue
    # Thanks https://stackoverflow.com/a/4233691
    elif  grep '^[[:space:]]*$' > /dev/null 2>&1 <<<"$line"; then
        continue
    fi
    inputLines+=("$line")
done

for line in "${inputLines[@]}"; do

    ghSourceOrg=$(cut -d/ -f1 <<<"$line")
    repo=$(cut -d/ -f2 <<<"$line")
    if [[ "$GH_ORG" != "${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}"  ]]; then
        api_response=$(gh api --hostname "$GH_SOURCE_HOST" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            "/repos/$ghSourceOrg/$repo")
        repoArchived=$(jq -r '.archived' <<<"$api_response")
        if [ "$repoArchived" = "false" ]; then
            newTopicPreMigration="github-cloud-migrating"
        else
            newTopicPreMigration="github-cloud-migrating-archive"
        fi
        check_and_replace_topic "$newTopicPreMigration" "true" "$repo" "$ghSourceOrg"
        archive_repo "true"
    else
        echo "Skipping archiving and topic updating as this is a sandbox migration"
    fi
    ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" -p 122  "$REMOTE_SCRIPT_DIR $ghSourceOrg $repo $GHE_TOKEN $GHE_USER $REMOTE_DATA_DIR" 2>&1 | tee "$DATA_DIR/eci-$ghSourceOrg-$repo.log"

done

rsync -avzr -progress -e "ssh -i $SSH_KEY -p 122" --include='*tar.gz' --exclude="*" $SSH_USER@$SSH_HOST:$REMOTE_ARCHIVE_DIR "$LOCAL_ARCHIVE_DIR"
