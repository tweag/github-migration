#!/usr/bin/env python3
# migrateGatorPullRequests.py
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
#     scripts/migrateGatorPullRequests.py <<<"org/github-migration,example-sb/github-migration"
#     scripts/migrateGatorPullRequests.py <<<"example-org/github-migration"

import json
import logging
import sys
from time import sleep

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
"""

logger = utils.getLogger(logging.INFO)

token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")

headers = utils.ghHeaders(token)


def getRepoPulls(org, repo, headers=headers, apiUrl=utils.GHEC_API_URL):
    url = "{}/repos/{}/{}/pulls".format(apiUrl, org, repo)
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)

    if res.status_code == 200:
        pulls = res.json()
        while "next" in res.links.keys():
            utils.ghRateLimitSleep(token, logger, instance="github.com")
            res = requests.get(
                res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
            )
            pulls.extend(res.json())
        return pulls
    elif res.status_code == 404:
        logger.info("No PR found in {}".format(url))
        return {}
    else:
        err = "Got {} error from {}, message: {}".format(
            res.status_code, url, res.json()
        )
        logger.error(err)
        raise Exception(err)


def getGatorPRList(org, repo, headers=headers, apiUrl=utils.GHEC_API_URL):
    pulls = getRepoPulls(org, repo, headers=headers, apiUrl=apiUrl)
    return [x for x in pulls if isGatorPocPullRequest(x, org)]


def isGatorPocPullRequest(pull, org):
    return (
        (
            "{}:gator-automated-pr-github-cloud-migration-".format(org)
            in pull["head"]["label"]
        )
        and ("POC - DO NOT MERGE - Migrate to github.com" in pull["title"])
        and pull["draft"]
    )


def patchGatorPr(pr, headers=headers):
    title = pr["title"]
    url = pr["url"]
    id = pr["node_id"]
    try:
        newTitle = title.split("DO NOT MERGE -", 1)[1].lstrip()
        body = pr["body"]
        newBody = body.replace("BR: XXX", "BR: YYY")
    except Exception as e:
        err = "Problem processing issue in PR {} with title {}".format(url, title)
        logger.error(err)
        raise e
    patch = {"title": newTitle, "body": newBody}
    logger.info(
        "Changing title for PR {} from '{}' to '{}'".format(url, title, newTitle)
    )
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    requests.patch(
        url, data=json.dumps(patch), headers=headers, timeout=DEFAULT_TIMEOUT
    )
    # GitHub asks that callers sleep at least 1 second betwen requests that mutate, see:
    # https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api?apiVersion=2022-11-28
    sleep(1)
    logger.info("Marking PR {} as ready to review".format(url))
    graphurl = "https://api.github.com/graphql"
    query = """
        mutation ($pullRequestId: ID!) {
            markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {
                clientMutationId
                pullRequest {
                    title
                    url
                }
            }
        }
    """
    variables = {"pullRequestId": id}
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    sleep(1)
    requests.post(
        graphurl,
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
    )


# BEGIN main logic of script
for line in sys.stdin:
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    repoDetails = utils.getRepoDetails(
        logger, destOrg, destRepo, headers=headers, apiUrl=utils.GHEC_API_URL
    )
    archived = repoDetails["archived"]
    if archived:
        logger.warning("Skipping {} as it is archived".format(line))
        continue
    # Get Gator PRs in GHEC
    prs = getGatorPRList(destOrg, destRepo, headers=headers, apiUrl=utils.GHEC_API_URL)
    logger.debug("Gator PRs detected: {}".format(prs))

    for pr in prs:
        logger.debug("processing PR {}".format(pr))
        patchGatorPr(pr)
