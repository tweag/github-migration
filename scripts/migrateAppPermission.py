#!/usr/bin/env python3
# migrateAppPermission.py
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
#     scripts/migrateAppPermission.py <<<"org/github-migration,org-sb/github-migration"
#     scripts/migrateAppPermission.py <<<"example-org/github-migration"

import logging
import sys
from time import sleep

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
cache = {}


def getInstalledApps(org, headers=sourceHeaders, apiUrl=utils.GHES_API_URL):
    utils.ghRateLimitSleep(sourceToken, logger)
    url = "{}/orgs/{}/installations".format(apiUrl, org)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    logger.info("Retrieving installed apps in org {} for {}".format(org, apiUrl))

    if res.status_code == 200:
        apps = res.json()["installations"]
        while "next" in res.links.keys():
            utils.ghRateLimitSleep(sourceToken, logger)
            res = requests.get(
                res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
            )
            apps.extend(res.json()["installations"])
        return apps
    elif res.status_code == 404:
        logger.info("No app found in {}".format(url))
        return {}
    else:
        err = "Got {} error from {}, message: {}".format(
            res.status_code, url, res.json()
        )
        logger.error(err)
        raise Exception(err)


def getInstalledAppRepos(installId, headers=sourceHeaders, apiUrl=utils.GHES_API_URL):
    url = "{}/user/installations/{}/repositories?per_page=100".format(apiUrl, installId)
    logger.debug("fetching repos for app with id {}".format(installId))
    utils.ghRateLimitSleep(sourceToken, logger)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)

    if res.status_code == 200:
        repos = res.json()["repositories"]
        while "next" in res.links.keys():
            utils.ghRateLimitSleep(sourceToken, logger)
            res = requests.get(
                res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
            )
            repos.extend(res.json()["repositories"])
        return repos
    elif res.status_code == 404:
        logger.info("No app found in {}".format(url))
        return {}
    else:
        err = "Got {} error from {}, message: {}".format(
            res.status_code, url, res.json()
        )
        logger.error(err)
        raise Exception(err)


def addRepoToInstalledApp(
    appId, repo, org, appName, ghecApps, headers=headers, apiUrl=utils.GHEC_API_URL
):
    installId = ""
    appSlug = (
        utils.GHES_TO_GHEC_APP_NAME_MATCH[appName]
        if utils.GHES_TO_GHEC_APP_NAME_MATCH.get(appName) is not None
        else appName
    )
    for app in ghecApps:
        if appSlug == app["app_slug"]:
            installId = app["id"]
            break
    if installId == "":
        sys.exit(
            "App named {} with slug {} not found in github cloud org {}, skipping".format(
                appName, appSlug, org
            )
        )

    if appId not in cache:
        cache[appId] = getInstalledAppRepos(
            appId, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
        )
    for appRepo in cache[appId]:
        if appRepo["name"] == repo:
            repoDetails = utils.getRepoDetails(logger, org, repo, headers, apiUrl)
            repoid = repoDetails["id"]
            url = "{}/user/installations/{}/repositories/{}".format(
                apiUrl, installId, repoid
            )
            logger.info("Adding repo {} to app {}".format(repo, appName))
            sleep(1)
            utils.ghRateLimitSleep(token, logger, instance="github.com")
            requests.put(url, headers=headers, timeout=DEFAULT_TIMEOUT)
            break


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

    ghesApps = getInstalledApps(
        sourceOrg, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
    )
    ghecApps = getInstalledApps(destOrg, headers=headers, apiUrl=utils.GHEC_API_URL)
    for app in ghesApps:
        if app["repository_selection"] == "all":
            logger.warning(
                "Skipping adding repo {} to app named {} in GHES as it is enabled for all repos, ensure this is done in GHEC".format(
                    destRepo, app["app_slug"]
                )
            )
            continue
        try:
            addRepoToInstalledApp(
                app["id"],
                destRepo,
                destOrg,
                app["app_slug"],
                ghecApps,
                headers=headers,
                apiUrl=utils.GHEC_API_URL,
            )
        except SystemExit as err:
            logger.warning(err)
            continue
