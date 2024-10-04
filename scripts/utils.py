#!/usr/bin/env python3
# utils.py

import base64

# Functions used by multiple scripts
import datetime
import functools as ft
import ipaddress
import json
import logging
import os
import re
import socket
import string
import sys
import time
from secrets import choice
from urllib.parse import urlparse

import __main__
import requests
from python_graphql_client import GraphqlClient

_SECRET_LENGTH = 40
_SECRET_CHARS = string.ascii_uppercase + string.ascii_lowercase + string.digits

# customize these as needed for your enterprise
DEFAULT_ORG = "org"
GHEC_API_URL = "https://api.github.com"
GHEC_PREFIX = "example"
GHEC_SANDBOX_ORG = "sb"
GHES_API_URL = "https://github.example.com/api/v3"
USER_SUFFIX = "example"
ORGS='org1
org2
'

# Thanks https://stackoverflow.com/a/19202904
COMMENT_RE = re.compile(r"^\s*(#.*|)$")

DEFAULT_TIMEOUT = 300


class UnexpectedStateError(Exception):
    """Raise when the state of the program has an unexpected condition.

    This is usually fatal."""

    pass


def getRandomToken(
    SECRET_LENGTH=_SECRET_LENGTH, SECRET_CHARS=_SECRET_CHARS, prefix="rwh_"
):
    # Thanks to https://stackoverflow.com/a/41464693
    newsecret = prefix + "".join([choice(SECRET_CHARS) for _ in range(SECRET_LENGTH)])
    return newsecret


def assertGetenv(envVar, message=""):
    env = os.getenv(envVar)
    if not env:
        raise AssertionError(
            "Environment variable '{}' not found. {}".format(envVar, message)
        )
    return env


class CustomFormatter(logging.Formatter):
    green = "\033[1;32m"
    grey = "\033[1;20m"
    yellow = "\033[1;33m"
    red = "\033[1;31m"
    bold_red = "\033[31;1m"
    reset = "\033[0m"
    # create formatter
    # The gh-gei formatter does this:
    # [2023-12-12 14:18:49] [INFO]
    # So thanks to https://stackoverflow.com/a/3220312 we can match
    fmt = "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s"

    FORMATS = {
        logging.DEBUG: green + fmt + reset,
        logging.INFO: grey + fmt + reset,
        logging.WARNING: yellow + fmt + reset,
        logging.ERROR: red + fmt + reset,
        logging.CRITICAL: bold_red + fmt + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, "%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def getLogger(level=logging.INFO, loggerName=""):
    # Set up logging per https://docs.python.org/3/howto/logging.html
    # Thanks https://stackoverflow.com/a/35514032 for the __main__ hint
    # create logger
    try:
        if not loggerName:
            loggerName = os.path.basename(__main__.__file__)
    except Exception:
        loggerName = __name__
    logger = logging.getLogger(loggerName)
    logger.setLevel(level)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # add formatter to ch
    ch.setFormatter(CustomFormatter())

    # add ch to logger
    logger.addHandler(ch)
    return logger


def getVaultSecretKeyName(hookDomain):
    return "{}".format(hookDomain.replace(".", "_").upper())


def getVaultPath(hookDomain):
    return "reverse-proxy/{}".format(getVaultSecretKeyName(hookDomain))


# TODO put in list of real prod domains to differentiate.
# Consider reading it in from a text file instead of hardcoding it here,
# if this list grows beyond a dozen or so.
DEV_HOOK_DESTINATIONS = ["some-destionation.example.com"]

PUBLIC_HOOK_DOMAIN_WITH_SECRET = [
    "admin.example.com",
]


def getVaultMountpoint(hookDomain):
    if hookDomain in DEV_HOOK_DESTINATIONS:
        namespace = "dev"
    else:
        namespace = "prod"
    return "langplats/{}/kv/secrets".format(namespace)


def isIpPrivate(domain, logger):
    try:
        ip = socket.gethostbyname(domain)
        isIpPrivate = ipaddress.ip_address(ip).is_private
    except socket.gaierror as err:
        isIpPrivate = True
        logger.info(
            "IP of {} is not resolvable, assigning as Private. Resolver message: {}".format(
                domain, err
            )
        )

    return isIpPrivate


def ghHeaders(ghAuthToken):
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": "Bearer {}".format(ghAuthToken),
    }


def ghGraphqlHeaders(ghAuthToken):
    return {
        "Graphql-Features": "gh_migrator_import_to_dotcom",
        "Authorization": "Bearer {}".format(ghAuthToken),
    }


def ghRateRemaining(ghAuthToken, instance="github.example.com"):
    # use requests to call rate_limit
    # pull out rate.remaining
    if instance == "github.com":
        url = "https://api.github.com/rate_limit"
    else:
        url = "https://{}/api/v3/rate_limit".format(instance)
    res = requests.get(url, headers=ghHeaders(ghAuthToken), timeout=DEFAULT_TIMEOUT)
    res.raise_for_status()
    return res.json()["rate"]["remaining"]


def ghRateResetSeconds(ghAuthToken, instance="github.example.com"):
    # use requests to call rate_limit
    # pull out rate.reset
    if instance == "github.com":
        url = "https://api.github.com/rate_limit"
    else:
        url = "https://{}/api/v3/rate_limit".format(instance)
    res = requests.get(url, headers=ghHeaders(ghAuthToken), timeout=DEFAULT_TIMEOUT)
    res.raise_for_status()
    resettime = res.json()["rate"]["reset"]
    dt_now = datetime.datetime.now()
    dt = datetime.datetime.fromtimestamp(resettime)
    result = dt - dt_now
    return result.seconds


def ghRateLimitSleep(ghAuthToken, logger, instance="github.example.com", threshold=120):
    remaining = ghRateRemaining(ghAuthToken, instance)
    if remaining < threshold:
        sleepTime = ghRateResetSeconds(ghAuthToken, instance) + threshold
        logger.info(
            f"Remaining ratelimit {remaining} is less than {threshold}, sleeping {sleepTime} seconds"
        )
        time.sleep(sleepTime)
    else:
        logger.debug(
            "Remaining ratelimit {} is at least {}, no sleep required".format(
                remaining, threshold
            )
        )


# Thanks https://stackoverflow.com/a/1883251 for the hint on reliably
# determining whether you are in a virtualenv
def get_base_prefix_compat():
    """Get base/real prefix, or sys.prefix if there is none."""
    return (
        getattr(sys, "base_prefix", None)
        or getattr(sys, "real_prefix", None)
        or sys.prefix
    )


def edit_scheme(url: str):
    schemeless = urlparse(url)._replace(scheme="").geturl()
    result = schemeless[2:] if schemeless.startswith("//") else schemeless
    return result, urlparse(url).scheme


def in_virtualenv():
    return sys.prefix != get_base_prefix_compat()


def getOrgAndRepo(line):
    repoPattern = re.compile("^([A-Za-z0-9-]+)/([A-Za-z0-9-_.]+)$")
    result = repoPattern.match(line)
    if not result:
        raise ValueError("Invalid org/repository name {}".format(line))
    return result.group(1), result.group(2)


def getOrgAndRepoPairs(line):
    repoPatternDual = re.compile(
        "^([A-Za-z0-9-]+)/([A-Za-z0-9-_.]+),([A-Za-z0-9-]+)/([A-Za-z0-9-_.]+)$"
    )
    result = repoPatternDual.match(line)
    if result:
        return result.group(1), result.group(2), result.group(3), result.group(4)
    else:
        (org, repo) = getOrgAndRepo(line)
        return org[8:], repo, org, repo


def createVaultSecret(
    logger, vaultUri, vaultHeaders, mount_point, vaultPath, hmacSecret
):
    secret = {
        "data": {
            "value": hmacSecret,
        }
    }

    url = "{}/{}/{}".format(vaultUri, mount_point, vaultPath)
    try:
        logger.info(
            "Writing secret to {} in {} with url {}".format(mount_point, vaultPath, url)
        )
        create_response = requests.post(
            url, data=json.dumps(secret), headers=vaultHeaders, timeout=DEFAULT_TIMEOUT
        )
        create_response.raise_for_status()
        logger.info(create_response.json())
    except Exception as e:
        logger.warning(e)
        logger.error(
            "Could not create secret in {} at {}".format(mount_point, vaultPath)
        )
        sys.exit(1)


def readOrCreateVaultSecret(logger, vaultUri, vaultHeaders, vaultPath, mount_point):
    try:
        logger.info("Retrieving secret {} from {}".format(vaultPath, mount_point))
        url = "{}/{}/{}".format(vaultUri, mount_point, vaultPath)
        read_response = requests.get(url, headers=vaultHeaders, timeout=DEFAULT_TIMEOUT)
        read_response.raise_for_status()
        hmacSecret = read_response.json()["data"]["data"]["value"]
    except requests.exceptions.HTTPError as e:
        logger.debug(read_response.json())
        if read_response.status_code == 400:
            logger.info(
                "No secret found under {} in {}, generating new HMAC secret, message={}".format(
                    mount_point, vaultPath, e
                )
            )
            hmacSecret = getRandomToken()
            # generate new random secret, upload to vault and assign this to the newsecret variable
            createVaultSecret(
                logger, vaultUri, vaultHeaders, mount_point, vaultPath, hmacSecret
            )
        else:
            logger.error(
                "{} Error occurred, message {}".format(
                    read_response.status_code, read_response.json()
                )
            )
            sys.exit(1)

    return hmacSecret


def getRepoDetails(logger, org, repo, headers, apiUrl=GHEC_API_URL):
    url = "{}/repos/{}/{}".format(apiUrl, org, repo)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)

    if res.status_code == 200:
        repoDetails = res.json()
        return repoDetails
    elif res.status_code == 404:
        logger.error("No repo found at {}".format(url))
        sys.exit(1)
    else:
        logger.error(
            "{} Error occurred, message {}".format(res.status_code, res.json())
        )
        sys.exit(1)


# Maps the name of apps in GHES to GHEC, this was crafted in 2024-02-04.
GHES_TO_GHEC_APP_NAME_MATCH = {
    "sourceapp": "destapp-ghec",
    "foo": "foo-ghec",
}

OLD_TO_NEW_WEBHOOK_HOSTNAME_MAP = {
    "cxflow.example.com": "cxflow.newexample.com",
}


def makeGetPrsQuery(org, repo, logger, count, qualifier=""):
    query = """
query Repository {
    repository(
        owner: "ORG"
        name: "REPO"
        followRenames: true
    ) {
        pullRequests(
          QUALIFIER
          orderBy: { direction: DESC, field: CREATED_AT},
          first: COUNT) {
            nodes {
                number
            }
          pageInfo {
            endCursor
            startCursor
            hasNextPage
            hasPreviousPage
         }
        }
    }
}
"""
    repls = (
        ("ORG", org),
        ("REPO", repo),
        ("COUNT", str(count)),
        ("QUALIFIER", qualifier),
    )
    res = ft.reduce(lambda a, kv: a.replace(*kv), repls, query)

    logger.debug(query)
    logger.debug(res)
    return res


def getLatestPR(
    org, repo, ghAuthToken, logger, graphqlUrl="https://api.github.com/graphql"
):
    client = GraphqlClient(endpoint=graphqlUrl)
    data = client.execute(
        query=makeGetPrsQuery(org, repo, logger, 1),
        headers=ghGraphqlHeaders(ghAuthToken),
    )
    logger.debug(json.dumps(data))
    return int(data["data"]["repository"]["pullRequests"]["nodes"][0]["number"])


def getOpenPRs(
    org, repo, ghAuthToken, logger, graphqlUrl="https://api.github.com/graphql"
):
    client = GraphqlClient(endpoint=graphqlUrl)
    # TODO: add loop to get all results
    morePages = True
    prs = []
    base_qualifier = "states: OPEN,"
    qualifier = base_qualifier
    while morePages:
        data = client.execute(
            query=makeGetPrsQuery(org, repo, logger, 100, qualifier=qualifier),
            headers=ghGraphqlHeaders(ghAuthToken),
        )
        logger.debug(json.dumps(data))
        prs.extend(
            [
                int(node["number"])
                for node in data["data"]["repository"]["pullRequests"]["nodes"]
            ]
        )
        morePages = data["data"]["repository"]["pullRequests"]["pageInfo"][
            "hasNextPage"
        ]
        if morePages:
            cursor = data["data"]["repository"]["pullRequests"]["pageInfo"]["endCursor"]
            qualifier = f'{base_qualifier} after: "{cursor}",'
    return prs


def createCommitQuery(
    org,
    repo,
    branch,
    file,
    fileContent,
    commitMsgHeadline,
    commitMsgBody,
    expectedHeadOid,
    logger,
):
    query = """
mutation CreateCommitOnBranch {
    createCommitOnBranch(
        input: {
            branch: { repositoryNameWithOwner: "REPO", branchName: "BRANCH" }
            fileChanges: {
                additions: [{ path: "FILE", contents: "CONTENTS" }]
            }
            message: { headline: "COMMITMSGHEADLINE", body: "COMMITMSGBODY" }
            expectedHeadOid: "HEADCOMMIT"
        }
    ) {
        clientMutationId
    }
}
"""
    fileContent_bytes = base64.b64encode(fileContent.encode("utf-8"))
    base64_string = fileContent_bytes.decode("ascii")
    repls = (
        ("REPO", f"{org}/{repo}"),
        ("BRANCH", branch),
        ("FILE", file),
        ("CONTENTS", base64_string),
        ("COMMITMSGHEADLINE", commitMsgHeadline),
        ("COMMITMSGBODY", commitMsgBody),
        ("HEADCOMMIT", expectedHeadOid),
    )
    res = ft.reduce(lambda a, kv: a.replace(*kv), repls, query)

    logger.debug(query)
    logger.debug(res)
    return res


def makeCommit(
    org,
    repo,
    ghAuthToken,
    branch,
    file,
    fileContent,
    commitMsgHeadline,
    commitMsgBody,
    sha,
    logger,
    graphqlUrl="https://api.github.com/graphql",
):
    client = GraphqlClient(endpoint=graphqlUrl)
    data = client.execute(
        query=createCommitQuery(
            org,
            repo,
            branch,
            file,
            fileContent,
            commitMsgHeadline,
            commitMsgBody,
            sha,
            logger,
        ),
        headers=ghGraphqlHeaders(ghAuthToken),
    )
    logger.debug(json.dumps(data))
