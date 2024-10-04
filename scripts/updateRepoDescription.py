#!/usr/bin/env python3
# updateRepoDescription.py
#
# Update Buildkite pipeline URLs to github.com equivalents of github.example.com.
# Takes a list of source,destination org/repo pairs of repositories from STDIN and migrate
#
# Accepts either:
#  source,destination org/repo pairs of repositories
#  destination org/repo pair of repositories

# Accepts either:
#  source,destination org/repo pairs of repositories
#  destination org/repo pair of repositories
#
# Usage:
#     scripts/updateRepoDescription.py <<<"org/github-migration,example-org/github-migration"
#     scripts/updateRepoDescription.py <<<"example-org/github-migration"
# or
#     scripts/updateRepoDescription.py < data/repoListPairs.txt``
#
# To mark all repos that have been migrated we could do:
#     cat data/migrations/webhookMap-* | sort -u | grep -Ev 'org1/excludeme' | scripts/updateRepoDescription.py

import datetime
import json
import logging
import os
import sys

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT, GHEC_PREFIX, GHEC_SANDBOX_ORG

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export GH_SOURCE_PAT=<The Personal Access Token from GHES>

# Optional Environment Variables
export GH_ORG=<GHEC org name>
"""

logger = utils.getLogger(logging.INFO)

token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
sourceToken = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a GitHub Enterprise Server personal access token"
)

headers = utils.ghHeaders(token)
sourceHeaders = {
    "Authorization": f"token {sourceToken}",
    "Graphql-Features": "gh_migrator_import_to_dotcom",
}

# Thanks https://stackoverflow.com/a/28147286
TIMESTAMP = datetime.datetime.now().replace(microsecond=0).isoformat()

MIGRATION_MESSAGE = "Migrated to https://github.com"
graphurl = "https://github.example.com/api/graphql"
gh_org = os.getenv("GH_ORG")


def updateRepoDesc(
    repo, org, description, apiUrl=utils.GHES_API_URL, headers=sourceHeaders
):
    url = "{}/repos/{}/{}".format(apiUrl, org, repo)
    payload = {"description": "{}".format(description)}
    res = requests.patch(
        url, json.dumps(payload), headers=headers, timeout=DEFAULT_TIMEOUT
    )
    return res


def archiveOrUnarchive(repoid, archive, graphurl, headers=sourceHeaders):
    if archive:
        query = """
            mutation ($repositoryId: ID!) {
                archiveRepository(input: { repositoryId: $repositoryId }) {
                    clientMutationId
                }
            }
        """
    else:
        query = """
            mutation ($repositoryId: ID!) {
                unarchiveRepository(input: { repositoryId: $repositoryId }) {
                    clientMutationId
                }
            }
        """
    variables = {"repositoryId": "{}".format(repoid)}
    requests.post(
        graphurl,
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
    )


def noneStr(s):
    return s is not None and s or ""


# Loop through the list of repos from STDIN
for line in sys.stdin:  # noqa: C901
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    sourceSlug = f"{sourceOrg}/{sourceRepo}"
    destSlug = f"{destOrg}/{destRepo}"
    repoDetails = utils.getRepoDetails(
        logger, sourceOrg, sourceRepo, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
    )
    if gh_org == f"{GHEC_PREFIX}-{GHEC_SANDBOX_ORG}":
        logger.warning(
            f"Skipping description update for {line} as the destination is ${GHEC_PREFIX}-${GHEC_SANDBOX_ORG}"
        )
        continue
    if repoDetails["archived"]:
        logger.info("unarchiving repo {}/{}".format(sourceOrg, sourceRepo))
        archiveOrUnarchive(
            repoDetails["node_id"], False, graphurl, headers=sourceHeaders
        )
    currentDescription = noneStr(repoDetails["description"])
    if (
        f":octocat: {MIGRATION_MESSAGE}/{GHEC_PREFIX}-{GHEC_SANDBOX_ORG}/{destRepo}"
        in str(currentDescription)
    ):
        currentDescription = str(currentDescription).split(":octocat:")[0]
    if MIGRATION_MESSAGE not in str(currentDescription):
        description = f"{currentDescription} :octocat: {MIGRATION_MESSAGE}/{destSlug} at {TIMESTAMP} :rocket:"
        logger.info(f"migrated repo {sourceSlug} updated description to: {description}")
        res = updateRepoDesc(
            sourceRepo,
            sourceOrg,
            description,
            apiUrl=utils.GHES_API_URL,
            headers=sourceHeaders,
        )
        logger.debug(res.json())
        if "Repository was archived so is read-only." in json.dumps(res.json()):
            logger.error(f"Repository {sourceSlug} archived, not updating description")
            sys.exit(1)
        elif res.status_code != 200:
            logger.warning(
                f"Updating repo description failed - status {res.status_code}"
            )
        if repoDetails["archived"]:
            logger.info("archiving repo {}/{}".format(sourceOrg, sourceRepo))
            archiveOrUnarchive(
                repoDetails["node_id"], True, graphurl, headers=sourceHeaders
            )
    else:
        logger.info(
            f"migrated repo {sourceSlug} already has migration text in description"
        )
        if repoDetails["archived"]:
            logger.info("archiving repo {}/{}".format(sourceOrg, sourceRepo))
            archiveOrUnarchive(
                repoDetails["node_id"], True, graphurl, headers=sourceHeaders
            )
