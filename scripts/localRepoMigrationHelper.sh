#!/usr/bin/env bash
# localRepoMigrationHelper.sh
#
# Summary
# -------
# This Bash script is designed to automate the process of checking and updating
# the migration status of Git repositories within a specified root directory.
#
# Prerequisites
# -------------
# * bash shell in macOS, Linux, or Windows WSL
# * The GitHub CLI (https://github.com/cli/cli#installation)to check repo migration status
#
# Description
# -----------
# The script checks whether each repository has been migrated to GitHub.com
# and updates the remote URL accordingly.
#
# The script works for org1, org2 and user repositories.
#
# By default this will scan the current working directory for repositories to a depth of 4 levels deep.
#
# You can change where it scans by specifying a directory to scan on the command line.
#
# You can change the MAX_DEPTH variable by specifying a second positional parameter.
# is set to depth of 4.
#
# Usage
# -----
#    ./localRepoMigrationHelper [directory-to-scan/] [max-depth]
#
# Example
# -------
#
# $ cd $HOME
# $ curl -O https://github.example.com/org1/github-migration/raw/main/scripts/localRepoMigrationHelper.sh
# $ chmod 755 localRepoMigrationHelper.sh
# $ ./localRepoMigrationHelper.sh Documents/org1
# INFO: updating /Users/luser/Documents/example/repo to git@github.com:example-org/repo.git

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
DEBUG=${DEBUG:-false}
$DEBUG && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

# Specify the root directory to start searching for repositories
ROOT_DIRECTORY=${1:-$(pwd)}

# Specify the maximum depth for recursive search
MAX_DEPTH=${2:-4}

# Specify your GitHub Enterprise Name
GITHUB_ENTERPRISE_NAME="github.example.com"

# Function to Check to see if the GitHub CLI is installed
function assertGhCliInstalled()
{

    if [[ -z "$(which gh)" ]]; then
        echo  "ERROR No installation of the GitHub CLI found. See https://github.com/cli/cli#installation"
        exit 1
    fi
}

# Function to check the migration status of a GitHub repository
check_migration_status() {
    local repo_path="$1"
    local slug
    local repo_name
    local organization
    local placeholder

    # Check if the repository uses HTTP or SSH
    local current_url
    current_url=$(git -C "$repo_path" remote get-url origin 2>/dev/null)
    slug=$(get_slug "$current_url")
    repo_name=$(cut -d/ -f 2 <<<"$slug")
    $DEBUG && echo "checking $repo_path for $repo_name having current_url: $current_url"

    if [[ "$current_url" =~ https://$GITHUB_ENTERPRISE_NAME ]]; then
        organization=$(echo "$current_url" | awk -F/ '{print $4}')
        $DEBUG && echo "Organization Name: $organization"
    elif [[ "$current_url" =~ git@$GITHUB_ENTERPRISE_NAME ]]; then
        organization=$(echo "$current_url" | awk -F'[:/]' '{print $2}')
        $DEBUG && echo "Organization Name: $organization"
    elif [[ "$current_url" =~ git@github.com|https://github.com ]]; then
        $DEBUG && echo "Remote url already updated"
        return
    else
        $DEBUG && echo "Ambiguous URL"
        return
    fi

    if [ "$organization" != "org1" ] && [ "$organization" != "org2" ]; then
        placeholder="${organization}_${GHEC_SUFFIX}"
        $DEBUG && echo "Organization: $organization"
    else
        placeholder="${GHEC_PREFIX}-${organization}"
        $DEBUG && echo "Excluded organization (org1 or org2) found."
    fi

    $DEBUG && echo "placeholder: $placeholder"

    # Check migration status using GitHub CLI
    if gh repo view "$placeholder/$repo_name" &> /dev/null ; then
        $DEBUG && echo "Repository $repo_name has been migrated."
        return 0
    else
        $DEBUG && echo "Repository $repo_name has not been migrated yet."
        return 1
    fi
}

# Function to get slug from GitHub URL
get_slug() {
    local current_url
    current_url=${1:-}
    sed 's/.*[/:]\(.*\/.*\)\.git/\1/' <<<"$current_url"
}

# Function to update the remote URL of a GitHub repository
update_remote_url() {
    local placeholder
    local repo_path="$1"
    local new_url
    local repo_name
    local slug

    # Check if the repository uses HTTP or SSH
    local current_url
    current_url=$(git -C "$repo_path" remote get-url origin 2>/dev/null || true)
    slug=$(get_slug "$current_url")
    repo_name=$(cut -d/ -f 2 <<<"$slug")

    if [[ "$current_url" =~ https://$GITHUB_ENTERPRISE_NAME ]]; then
        # Replace GitHub Enterprise URL with GitHub.com URL for HTTP
        organization=$(echo "$current_url" | awk -F/ '{print $4}')
            if [ "$organization" != "org1" ] && [ "$organization" != "org2" ]; then
                placeholder="${organization}_${GHEC_SUFFIX}"
                $DEBUG && echo "Username in update url: $organization"
            else
                placeholder="${GHEC_PREFIX}-${organization}"
                $DEBUG && echo "Organization (org1 or org2) found in update url."
            fi

        new_url="https://github.com/$placeholder/$repo_name.git"

    elif [[ "$current_url" =~ git@$GITHUB_ENTERPRISE_NAME ]]; then
        # Replace GitHub Enterprise URL with GitHub.com URL for SSH
        organization=$(echo "$current_url" | awk -F'[:/]' '{print $2}')
            if [ "$organization" != "org1" ] && [ "$organization" != "org2" ]; then
                placeholder="${organization}_${GHEC_SUFFIX}"
                $DEBUG && echo "Username in update url: $organization"
            else
                placeholder="${GHEC_PREFIX}-${organization}"
                $DEBUG && echo "Organization (org1 or org2) found in update url."
            fi
        new_url="git@github.com:$placeholder/$repo_name.git"
    else
        $DEBUG && echo "URL is already updated or unknown remote URL for $(basename "$repo_path") in $repo_path. Skipping..."
        return
    fi

    # Update remote URL
    git -C "$repo_path" remote set-url origin "$new_url"
    echo "INFO: updating $repo_path to $new_url"
}

# Function to check if a directory contains a Git repository
is_git_repo() {
    local directory="$1"
    [ -d "$directory/.git" ] && git -C "$directory" rev-parse --is-inside-work-tree &> /dev/null
}

# function to search for GitHub repositories
search_and_migrate() {
    find "$1" -maxdepth "$MAX_DEPTH" -type d | while read -r item; do
        $DEBUG && echo "Checking $item"
        if is_git_repo "$item"; then
            if check_migration_status "$item"; then
                update_remote_url "$item"
            else
                echo "INFO: skipping $item, no migration required"
            fi
        fi
    done
}

#Calling GitHub CLI check
assertGhCliInstalled

# Start the search and migration process
search_and_migrate "$ROOT_DIRECTORY"
