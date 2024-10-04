#!/usr/bin/env python3
# migrateGhPages.py
#
# Migrate permissions for repos on org apps from GHES to GHEC
#
# Takes a list of source,destination org/repo pairs of repositories from STDIN and migrate
#
# Accepts either:
#  source,destination org/repo pairs of repositories
#  source org/repo pair of repositories
#
# Usage:
#     scripts/migrateGhPages.py <<<"org/github-migration,example-org/github-migration"
#     scripts/migrateGhPages.py <<<"example-org/github-migration"

import json
import logging
import sys

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export GH_SOURCE_PAT=<The Personal Access Token from GHES>
"""

logger = utils.getLogger(logging.INFO)

token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
sourceToken = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a GitHub Enterprise Server personal access token"
)

headers = utils.ghHeaders(token)
sourceHeaders = {
    "Authorization": f"token {sourceToken}",
}


def getGhPages(repo, org, headers=sourceHeaders, apiUrl=utils.GHES_API_URL):
    utils.ghRateLimitSleep(sourceToken, logger)
    url = "{}/repos/{}/{}/pages".format(apiUrl, org, repo)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    logger.info("Retrieving github pages in {}/{}".format(org, repo))

    if res.status_code == 200:
        page = res.json()["source"]
        return page
    elif res.status_code == 404:
        logger.info("No page found in {}".format(repo))
        return {}
    else:
        err = "Got {} error from {}, message: {}".format(
            res.status_code, url, res.json()
        )
        logger.error(err)
        raise Exception(err)


def enableGhPages(repo, org, config, headers=headers, apiUrl=utils.GHEC_API_URL):
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    url = "{}/repos/{}/{}/pages".format(apiUrl, org, repo)
    logger.info("Adding gh pages to {}/{}".format(org, repo))
    logger.info("{}".format(config))
    requests.post(url, json.dumps(config), headers=headers, timeout=DEFAULT_TIMEOUT)


# BEGIN main logic of script

for line in sys.stdin:
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    repoDetails = utils.getRepoDetails(
        logger, destOrg, destRepo, headers=headers, apiUrl=utils.GHEC_API_URL
    )
    archived = repoDetails["archived"]
    if archived:
        logger.warning("Skipping {} as it is archived".format(line))
        continue

    ghPagesSource = getGhPages(
        sourceRepo, sourceOrg, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
    )
    if ghPagesSource:
        config = {"source": ghPagesSource}
        enableGhPages(
            destRepo, destOrg, config=config, headers=headers, apiUrl=utils.GHEC_API_URL
        )
