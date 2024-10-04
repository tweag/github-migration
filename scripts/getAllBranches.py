#!/usr/bin/env python3
# getAllBranches.py
#
# Retrieve all archived repos in a list
# Usage:
# scripts/getAllBranches.py <<<"org/repo,prefix-org/repo"

import sys

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT

logger = utils.getLogger()
token = utils.assertGetenv(
    "GH_PAT", "Provide a personal access token from the source GHES instance"
)

headers = utils.ghHeaders(token)


def getBranches(url, headers=headers):
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    if res.status_code == 200:
        branches = res.json()
        while "next" in res.links.keys():
            res = requests.get(
                res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
            )
            branches.extend(res.json())
        return branches
    elif res.status_code == 404:
        logger.info("No Branches found in {}".format(url))
        return {}
    else:
        logger.error(
            "Got {} error from {}, message: {}".format(res.status_code, url, res.json())
        )
        sys.exit(1)


# BEGIN main logic of script
for line in sys.stdin:  # noqa: C901
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    url = f"{utils.GHEC_API_URL}/repos/{destOrg}/{destRepo}/branches?per_page=100"
    branchJson = getBranches(url, headers=headers)
    with open(f"{sourceRepo}_branchList.txt", "w") as f:
        for branch in branchJson:
            f.write(f"{branch['name']}\n")
