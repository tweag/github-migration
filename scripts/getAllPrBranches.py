#!/usr/bin/env python3
# getAllBranches.py
#
# Retrieve all archived repos in a list
# Usage:
# scripts/getAllPrBranches.py <<<"org/repo,prefix-org/repo"

import sys

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT

logger = utils.getLogger()
token = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a personal access token from the source GHES instance"
)

headers = utils.ghHeaders(token)


def getPrByRange(repo, org, firstNum, headers=headers):
    prs = []
    runLoop = True
    prNum = firstNum
    while runLoop:
        url = f"{utils.GHES_API_URL}/repos/{org}/{repo}/pulls/{prNum}"
        res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200:
            prs.append(res.json())
        else:
            logger.error(
                f"Got {res.status_code} error from {url}, message: {res.json()}"
            )
            runLoop = False
        prNum += 1
    return prs


# BEGIN main logic of script
for line in sys.stdin:  # noqa: C901
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    prList = getPrByRange(sourceRepo, sourceOrg, 124398, headers=headers)
    with open(f"{sourceRepo}_PrbranchList.txt", "w") as f:
        for pr in prList:
            f.write(f"{pr['head']['ref']},{pr['base']['sha']}\n")
