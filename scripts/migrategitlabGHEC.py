#!/usr/bin/env python3
# migrategitlabGHEC.py
#
# undraft Gator pull requests for one or more GitHub repositories that
# are now on GitHub Enterprise Cloud.
#
# Takes a list of source,destination org/repo pairs of repositories from STDIN and migrate
#
# Accepts either:
#  source,destination org/repo pairs of repositories
#  source org/repo pair of repositories
#
# Usage:
#     scripts/migrategitlabGHEC.py < data/repoList.csv

import csv
import subprocess
import os
import requests
from pathlib import Path
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT, USER_SUFFIX, UnexpectedStateError
import time
import sys

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export GITLAB_TOKEN=<The Personal Access Token from GitLab>

# Optional Environment Variables
export GH_ORG=<GHEC org name>
"""

logger = utils.getLogger()


GH_PAT = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
GITLAB_TOKEN = utils.assertGetenv(
    "GITLAB_TOKEN", "Provide a GitLab personal access token"
)
GITLAB_USERNAME = utils.assertGetenv(
    "GITLAB_USERNAME", "Provide your GitLab username"
)
GH_ORG = utils.assertGetenv(
    "GH_ORG", "Provide your GitHub Org"
)

headers = {
    "Authorization": f"token {GH_PAT}",
    "Graphql-Features": "gh_migrator_import_to_dotcom,octoshift_gl_exporter,octoshift_github_owned_storage"
}


# Configuration
CSV_FILE = 'data/migrations/export.csv'
DOCKER_IMAGE = 'gl-exporter:v1'
GITLAB_SERVER = "http://gitlab.uzomanwoko.com:8000"
TESTGITLAB_SERVER = "http://gitlab.uzomanwoko.com"
CONTINUE_ON_ERROR = True
TARGET_REPO_VISIBILITY = 'private'  # or 'INTERNAL' or 'PUBLIC'
WORKDIR = f"{os.getcwd()}/data/migrations"
# GraphQL API endpoint
GITHUB_GRAPHQL_URL = 'https://api.github.com/graphql'
POLL_INTERVAL = 5  # seconds between status checks
MAX_ATTEMPTS = 600  # max status checks (5 * 600 = 1 hour max wait)


def get_migration_status(migration_id):
    """Check the status of a repository migration"""
    query = """
    query ($id: ID!) {
        node(id: $id) {
            ... on Migration {
                id
                sourceUrl
                migrationSource {
                    name
                }
                state
                failureReason
            }
        }
    }
    """
    
    variables = {'id': migration_id}
    response = make_graphql_request(query, variables)
    if not response or 'errors' in response['data']:
        logger.warning(
            f"Error checking migration status for {migration_id}: {response['data']}"
        )
        return None
    
    return response['data']['node']

def monitor_migrations(migration_ids):
    """Monitor multiple migrations until all are complete"""
    completed_migrations = {}
    pending_migrations = migration_ids.copy()
    attempts = 0
    logger.info(
            f"Starting to monitor {len(pending_migrations)} migrations..."
        )

    while pending_migrations and attempts < MAX_ATTEMPTS:
        attempts += 1
        logger.info(
            f"Polling attempt {attempts} of {MAX_ATTEMPTS}"
        )
        # Check each pending migration
        for migration_id in list(pending_migrations.keys()):
            status = get_migration_status(migration_id)
            
            if not status:
                continue
            
            repo_name = pending_migrations[migration_id]
            logger.info(
                f"Migration {migration_id} ({repo_name}): {status['state']}"
            )
            
            if status['state'] in ['SUCCEEDED', 'FAILED']:
                completed_migrations[migration_id] = {
                    'repo': repo_name,
                    'status': status['state'],
                    'reason': status.get('failureReason'),
                    'details': status
                }
                del pending_migrations[migration_id]                
        
        if pending_migrations:
            logger.info(
                f"Waiting {POLL_INTERVAL} seconds before next check..."
            )
            time.sleep(POLL_INTERVAL)
    
    # Final status report
    logger.info("\nMigration monitoring completed:")
    logger.info(f"- Total migrations: {len(migration_ids)}")
    logger.info(f"- Succeeded: {len([m for m in completed_migrations.values() if m['status'] == 'SUCCEEDED'])}")
    logger.info(f"- Failed: {len([m for m in completed_migrations.values() if m['status'] == 'FAILED'])}")
    logger.info(f"- Still pending: {len(pending_migrations)}")
    
    return completed_migrations

def read_repos_from_csv():
    """Read repositories from CSV file"""
    repos = []
    with open(CSV_FILE, mode='r') as csv_file:
        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            if len(row) >= 2:
                repos.append((row[0].strip(), row[1].strip()))
    return repos

def export_gitlab_repo(group, project):
    """Export a GitLab repository using Docker"""
    archive_name = f"{group}-{project}-migration-archive.tar.gz"
    cmd = [
        'docker', 'run',
        '-v', f"{WORKDIR}:/workspace",
        '--workdir', '/workspace',
        '-e', f"GITLAB_API_PRIVATE_TOKEN={GITLAB_TOKEN}",
        '-e', f"GITLAB_API_ENDPOINT={GITLAB_SERVER}/api/v4",
        '-e', f"GITLAB_USERNAME={GITLAB_USERNAME}",
        '--network=host',
        DOCKER_IMAGE,
        'gl_exporter',
        '--namespace', group,
        '--project', project,
        '--out-file', f"/workspace/{archive_name}"
    ]
    logger.info(
        f"Exporting {group}/{project} from GitLab..."
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(
            f"Error exporting {group}/{project}: {result.stderr}"
        )
        return None
    
    return archive_name

def get_github_org_id(org):
    """Get GitHub organization ID using GraphQL"""
    query = """
    query($login: String!) {
      organization(login: $login) {
        login
        id
        name
        databaseId
      }
    }
    """
    
    variables = {'login': org}
    response = make_graphql_request(query, variables)
    
    if not response or 'errors' in response:
        logger.error(
            "Error getting GitHub organization ID"
        )
        logger.debug(
            f"Error: {response}"
        )
        return None
    
    return [response['data']['organization']['id'], response['data']['organization']['databaseId']]

def create_migration_source(owner_id):
    """Create a migration source in GitHub"""
    mutation = """
    mutation createMigrationSource($name: String!, $ownerId: ID!) {
      createMigrationSource(input: {name: $name, url: "https://github.com", ownerId: $ownerId, type: GL_EXPORTER_ARCHIVE}) {
        migrationSource {
          id
          name
          url
          type
        }
      }
    }
    """
    
    variables = {
        'name': 'GitLab Migration Source',
        'ownerId': owner_id
    }
    
    response = make_graphql_request(mutation, variables)
    
    if not response or 'errors' in response:
        logger.error(
            "Error creating migration source"
        )
        logger.debug(
            f"Error: {response}"
        )
        return None
    
    return response['data']['createMigrationSource']['migrationSource']['id']

def upload_archive_to_github(archive_path, org_id):
    """Upload archive to GitHub"""
    url = f"https://uploads.github.com/organizations/{org_id}/gei/archive?name={os.path.basename(archive_path)}"
    
    headers = {
        'Authorization': f"Bearer {GH_PAT}",
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/octet-stream'
    }
    
    try:
        with open(archive_path, 'rb') as f:
            response = requests.post(url, headers=headers, data=f)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(
            f"Error uploading archive: {e}"
        )
        return None

def start_repository_migration(source_id, owner_id, repo_name, group, git_archive_url, metadata_archive_url):
    """Start repository migration"""
    mutation = """
    mutation startRepositoryMigration(
        $sourceId: ID!
        $ownerId: ID!
        $repositoryName: String!
        $continueOnError: Boolean!
        $accessToken: String!
        $githubPat: String!
        $gitArchiveUrl: String!
        $metadataArchiveUrl: String!
        $sourceRepositoryUrl: URI!
        $targetRepoVisibility: String!
    ) {
        startRepositoryMigration(
            input: {
                sourceId: $sourceId
                ownerId: $ownerId
                repositoryName: $repositoryName
                continueOnError: $continueOnError
                accessToken: $accessToken
                githubPat: $githubPat
                targetRepoVisibility: $targetRepoVisibility
                gitArchiveUrl: $gitArchiveUrl
                metadataArchiveUrl: $metadataArchiveUrl
                sourceRepositoryUrl: $sourceRepositoryUrl
            }
        ) {
            repositoryMigration {
                id
                migrationSource {
                    id
                    name
                    type
                }
                sourceUrl
            }
        }
    }
    """
    
    variables = {
        'sourceId': source_id,
        'ownerId': owner_id,
        'repositoryName': repo_name,
        'continueOnError': CONTINUE_ON_ERROR,
        'accessToken': GITLAB_TOKEN,
        'githubPat': GH_PAT,
        'gitArchiveUrl': git_archive_url,
        'metadataArchiveUrl': metadata_archive_url,
        'sourceRepositoryUrl': f"{TESTGITLAB_SERVER}/{group}/{repo_name}",
        'targetRepoVisibility': TARGET_REPO_VISIBILITY
    }
    
    response = make_graphql_request(mutation, variables)
    
    if not response or 'errors' in response:
        logger.error(
            "Error creating migration source"
        )
        logger.debug(
            f"Error: {response}"
        )
        return None
    
    return response['data']['startRepositoryMigration']['repositoryMigration']

def make_graphql_request(query, variables):
    """Make a GraphQL request to GitHub API""" 
    payload = {
        'query': query,
        'variables': variables
    }
    
    try:
        response = requests.post(GITHUB_GRAPHQL_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(
            f"GraphQL request failed: {e}"
        )
        return None

def gitHubRepoExists(org, repo, headers, apiUrl):
    url = "{}/repos/{}/{}".format(apiUrl, org, repo)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)

    if res.status_code == 200:
        logger.warning("Repo already exists at {}, Skipping".format(url))
        return True
    elif res.status_code == 404:
        return False
    else:
        logger.error(
            "{} Error occurred, message {}".format(res.status_code, res.json())
        )
        sys.exit(1)

def main():

    # Get GitHub organization ID
    org_id,databaseId = get_github_org_id(GH_ORG)
    logger.info(
        f"Org Id is {org_id}"
    )
    if not org_id:
        return
    
    # Create migration source
    source_id = create_migration_source(org_id)
    if not source_id:
        return
    
    # Read repositories from CSV
    repos = read_repos_from_csv()
    if not repos:
        logger.warning(
            "No repositories found in CSV file"
        )
        return
    migration_ids = {}  # {migration_id: repo_name}
    
    # Process each repository
    for group, project in repos:
        if gitHubRepoExists(GH_ORG, project, headers, utils.GHEC_API_URL):
            continue
        utils.ghRateLimitSleep(GH_PAT, logger, instance="github.com")
        logger.info(f"Processing {group}/{project}")
        
        # Step 1: Export from GitLab
        archive_name = export_gitlab_repo(group, project)
        if not archive_name:
            continue
        
        archive_path = Path(f"{WORKDIR}/{archive_name}")
        if not archive_path.exists():
            logger.warning(f"Archive {archive_name} not found")
            continue
        
        # Step 2: Upload archive to GitHub
        upload_response = upload_archive_to_github(archive_path, databaseId)
        logger.info(f"Uploaded archive uri is {upload_response['uri']}")
        if not upload_response:
            continue
        
        archive_url = upload_response.get('uri')
        
        if not archive_url:
            
            logger.warning("Upload response missing required URLs")
            continue
        
        # Step 3: Start migration
        migration = start_repository_migration(
            source_id=source_id,
            owner_id=org_id,
            repo_name=project,
            group=group,
            git_archive_url=archive_url,
            metadata_archive_url=archive_url
        )
        if migration:
            migration_id = migration['id']
            migration_ids[migration_id] = project
            logger.info(f"Migration started successfully for {group}/{project}")
            logger.info(f"Migration ID: {migration['id']}")
            logger.info(f"Source URL: {migration['sourceUrl']}")
        else:
            logger.error(f"Failed to start migration for {group}/{project}")
        
        # Clean up archive file
        try:
            archive_path.unlink()
            logger.info(f"Removed archive file: {archive_name}")
        except Exception as e:
            logger.warning(f"Error removing archive file: {e}")

    # Monitor all migrations
    if migration_ids:
        completed_migrations = monitor_migrations(migration_ids)
        
        # Print detailed results
        logger.info("\nMigration Results:")
        for migration_id, details in completed_migrations.items():
            status = "✅ SUCCEEDED" if details['status'] == 'SUCCEEDED' else f"❌ FAILED ({details['reason']})"
            logger.info(f"{status} - {details['repo']} (ID: {migration_id})")
    else:
        logger.warning("No migrations were started")

if __name__ == '__main__':
    main()