#!/usr/bin/env python3
# getAllOpenPrs.py
#
# Get all open pull requests in a migrated repository
# Usage:
# scripts/getAllOpenPrs <<<"org/repo,prefix-org/repo"

import logging
import sys

import utils
from utils import COMMENT_RE, getOpenPRs

logLevel = logging.INFO
logging.basicConfig(level=logLevel)
logger = utils.getLogger(logLevel)

token = utils.assertGetenv("GH_PAT", "Provide a personal access token for github.com")


def getAllOpenPRs(org, repo, token, logger):
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    openPrs = getOpenPRs(org, repo, token, logger)
    logger.info(f"getAllOpenPRs: {len(openPrs)} PRs found: {openPrs}")


# BEGIN main logic of script
for line in sys.stdin:
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    getAllOpenPRs(destOrg, destRepo, token, logger)
