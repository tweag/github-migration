#!/usr/bin/env python3
# getWebhookList.py
#
# Retrieve all archived repos in a list
# Usage:
# scripts/getArchivedRepo.py < data/repoList.txt

import sys

import utils
from utils import COMMENT_RE

logger = utils.getLogger()
token = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a personal access token from the source GHES instance"
)
headers = utils.ghHeaders(token)

repoList = []
# BEGIN main logic of script
for line in sys.stdin:  # noqa: C901
    if COMMENT_RE.match(line):
        continue
    repo = line.strip()
    repobreak = repo.split("/", 1)

    repoDetails = utils.getRepoDetails(
        logger, repobreak[0], repobreak[1], headers, apiUrl=utils.GHES_API_URL
    )
    archived = repoDetails["archived"]
    if archived:
        repoList.append(repoDetails["full_name"])
logger.info("\n" + "\n".join(repoList))
