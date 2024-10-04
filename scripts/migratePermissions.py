#!/usr/bin/env python3
# migratePermissions.py
#
# Migrate user and teams permissions for one or more GitHub repositories that
# are now on GitHub Enterprise Cloud.
#
# Takes a list of source,destination org/repo pairs of repositories from STDIN and migrate
#
# Accepts either:
#  source,destination org/repo pairs of repositories
#  destination org/repo pair of repositories
#
# Usage:
#     scripts/migratePermissions.py <<<"org/github-migration,example-org/github-migration"
#     scripts/migratePermissions.py <<<"example-org/github-migration"
# or
#     scripts/migratePermissions.py < data/repoListPairs.txt

import json
import sys

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT, USER_SUFFIX

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export GH_SOURCE_PAT=<The Personal Access Token from GHES>

# Optional Environment Variables
export GH_ORG=<GHEC org name>
"""

logger = utils.getLogger()


token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
sourceToken = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a GitHub Enterprise Server personal access token"
)

headers = {
    "Authorization": f"token {token}",
}
sourceHeaders = {
    "Authorization": f"token {sourceToken}",
}


def getRepoCollaborators(url, headers=sourceHeaders):
    utils.ghRateLimitSleep(sourceToken, logger, threshold=120)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    if res.status_code == 200:
        collabs = res.json()
        while "next" in res.links.keys():
            res = requests.get(
                res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
            )
            collabs.extend(res.json())
        return collabs
    elif res.status_code == 404:
        logger.info("No collaborators found in {}".format(url))
        return {}
    else:
        logger.error(
            "Got {} error from {}, message: {}".format(res.status_code, url, res.json())
        )
        sys.exit(1)


def putRepoCollabs(url, collabPermission, headers=headers):
    payload = {"permission": collabPermission}
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    res = requests.put(
        url, json.dumps(payload), headers=headers, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code == 201:
        logger.info("New invite has been sent, url: {}".format(url))
    elif res.status_code == 204:
        logger.info(
            "Completed action of adding permission {} to repo url: {}".format(
                collabPermission, url
            )
        )
        return {}
    elif (
        res.status_code == 403 and res.json().message == "Repository has been locked"
    ) or (
        res.status_code == 422
        and res.json().message == "This repository is locked and cannot be modified"
    ):
        logger.warning(
            "Repository locked - got {} from {}: {}".format(
                res.status_code, url, res.json()
            )
        )
        return {}
    elif res.status_code == 404:
        logger.warning(
            "Could not create collaborator, likely user not found {}".format(url)
        )
        return {}
    else:
        logger.error(
            "Got {} error from {}, message: {}".format(res.status_code, url, res.json())
        )
        sys.exit(1)


# BEGIN main logic of script
# Loop through the list of repos from STDIN
for line in sys.stdin:  # noqa: C901
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    repoDetails = utils.getRepoDetails(
        logger, destOrg, destRepo, headers, apiUrl=utils.GHEC_API_URL
    )
    archived = repoDetails["archived"]
    if archived:
        logger.warning("Skipping {} as it is archived".format(line))
        continue
    # Get User collaborators
    url = "{}/repos/{}/{}/collaborators?affiliation=direct".format(
        utils.GHES_API_URL, sourceOrg, sourceRepo
    )
    userCollabs = getRepoCollaborators(url, headers=sourceHeaders)
    # Get Team collaborators
    url = "{}/repos/{}/{}/teams".format(utils.GHES_API_URL, sourceOrg, sourceRepo)
    teamCollabs = getRepoCollaborators(url, headers=sourceHeaders)

    for collab in userCollabs:
        collabLogin = collab["login"]
        permissions = ["admin", "maintain", "push", "triage", "pull"]
        for perm in permissions:
            if collab["permissions"][perm]:
                collabPermission = perm
                break
        logger.debug(
            "processing permission for user collaborator {} with {} permissions for repo {}".format(
                collabLogin, collabPermission, sourceRepo
            )
        )
        url = "{}/repos/{}/{}/collaborators/{}_{}".format(
            utils.GHEC_API_URL, destOrg, destRepo, collabLogin, USER_SUFFIX
        )
        putRepoCollabs(url, collabPermission)
    for collab in teamCollabs:
        url = "{}/orgs/{}/teams/{}/repos/{}/{}".format(
            utils.GHEC_API_URL, destOrg, collab["slug"], destOrg, destRepo
        )
        permissions = ["admin", "maintain", "push", "triage", "pull"]
        for perm in permissions:
            if collab["permissions"][perm]:
                collabPermission = perm
                break
        logger.debug(
            "processing permission for team collaborator {} with {} permissions for repo {}".format(
                collab["slug"], collabPermission, sourceRepo
            )
        )
        putRepoCollabs(url, collabPermission, headers=headers)
