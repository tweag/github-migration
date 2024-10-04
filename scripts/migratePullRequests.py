#!/usr/bin/env python3
# migratePullRequests.py
#
# Takes a list of source,destination org/repo pairs of repositories from STDIN
# and migrates pull requests and issues that are missing on the destination from the
# source.
#
# Accepts either:
#  source,destination org/repo pairs of repositories
#  destination org/repo pair of repositories
#
# Usage:
#     scripts/migratePullRequests.py <<<"org/github-migration,example-org/github-migration"
#     scripts/migratePullRequests.py <<<"example-org/github-migration"
# or
#     scripts/migratePullRequests.py < data/repoListPairs.txt
#
# or keep a log:
#     source scripts/common.sh
#     useSystemCAForPython
#     time scripts/migratePullRequests.py <<<"org1/github-migration,example-org/github-migration" 2>&1 | tee data/migrations/migratePullRequests-$(iso8601_win_safe_ts).log

import json
import os
import sys
from time import sleep

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT, USER_SUFFIX, UnexpectedStateError

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export GH_SOURCE_PAT=<The Personal Access Token from GHES>
export DRY_RUN=<true or false - only really create PRs if true>
# Optional Environment Variables
export CHECK_CLOSED_PRS=<true or false - false by default>
export LOG_LEVEL=DEBUG
"""

token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
sourceToken = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a GitHub Enterprise Server personal access token"
)
prNumCreated = 0

headers = utils.ghHeaders(token)
sourceHeaders = utils.ghHeaders(sourceToken)

exitCode = 0

dryRun = True if os.getenv("DRY_RUN", "false") == "true" else False
checkClosedPrs = True if os.getenv("CHECK_CLOSED_PRS", "false") == "true" else False
logLevel = os.getenv("LOG_LEVEL", "INFO")

logger = utils.getLogger(logLevel)


def longSleep():
    sleep(5)


def getRepoPrDetails(
    org, repo, prNum, apiUrl=utils.GHES_API_URL, headers=sourceHeaders
):
    url = f"{apiUrl}/repos/{org}/{repo}/pulls/{prNum}"
    sleep(1)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    if res.status_code == 200:
        prs = res.json()
        return prs
    elif res.status_code == 404:
        logger.info(f"No pr found in {url}")
        return {}
    else:
        message = f"Got {res.status_code} error from {url}, message: {res.json()}"
        raise UnexpectedStateError(message)


def getRepoIssuesDetails(
    org, repo, prNum, apiUrl=utils.GHES_API_URL, headers=sourceHeaders
):
    url = f"{apiUrl}/repos/{org}/{repo}/issues/{prNum}"
    sleep(1)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    if res.status_code == 200:
        prs = res.json()
        return prs
    elif res.status_code == 404:
        logger.info(f"No issue found in {url}")
        return {}
    else:
        message = f"Got {res.status_code} error from {url}, message: {res.json()}"
        raise UnexpectedStateError(message)


def getRepoPrComments(url, headers=sourceHeaders):
    sleep(1)
    res = requests.get(
        url, headers=headers, params={"per_page": "100"}, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code == 200:
        comments = res.json()
        return comments
    elif res.status_code == 404:
        logger.info(f"No pr found in {url}")
        return {}
    else:
        message = f"Got {res.status_code} error from {url}, message: {res.json()}"
        raise UnexpectedStateError(message)


def createPrOrIssue(url, body, num, headers=headers):
    message = f"Creating PR or issue {url}/{num}"
    logger.info(message)
    body_json = json.dumps(body)
    if dryRun:
        logger.info(f"Dry run - {message}")
        logger.debug(body_json)
        return num

    logger.debug(body)
    longSleep()
    res = requests.post(url, body_json, headers=headers, timeout=DEFAULT_TIMEOUT)
    if res.status_code == 201:
        return res.json()["number"]
    else:
        message = f"Got {res.status_code} error from {url}, message: {res.json()}"
        raise UnexpectedStateError(message)


def checkBranch(branch, org, repo, apiUrl=utils.GHEC_API_URL):
    url = f"{apiUrl}/repos/{org}/{repo}/branches/{branch}"
    message = f"Checking branch {url}"
    logger.debug(message)
    sleep(1)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    logger.debug(res)
    if res.status_code == 200:
        return True
    else:
        return False


def checkPrNum(prNum, org, repo, apiUrl=utils.GHEC_API_URL):
    url = f"{apiUrl}/repos/{org}/{repo}/pulls/{prNum}"
    sleep(1)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    if res.status_code == 200:
        return True
    else:
        return False


def createBranch(branch, sha, org, repo, apiUrl=utils.GHEC_API_URL):
    message = f"Creating branch {branch} for {org}/{repo} at {sha}"
    logger.info(message)
    if dryRun:
        logger.info(f"Dry run - {message}")
        return
    url = f"{apiUrl}/repos/{org}/{repo}/git/refs".format(apiUrl, org, repo)
    body = {"ref": f"refs/heads/{branch}", "sha": f"{sha}"}
    longSleep()
    requests.post(url, json.dumps(body), headers=headers, timeout=DEFAULT_TIMEOUT)


def delBranch(branch, org, repo, apiUrl=utils.GHEC_API_URL):
    message = f"Deleting branch {branch} for {org}/{repo} using {apiUrl}"
    logger.info(message)
    if dryRun:
        logger.info(f"Dry run - {message}")
        return
    url = f"{apiUrl}/repos/{org}/{repo}/git/refs/{branch}"
    longSleep()
    requests.delete(url, headers=headers, timeout=DEFAULT_TIMEOUT)


def createPrOrIssueObject(url, body, headers=headers):
    message = f"Creating object {url}"
    logger.info(message)
    if dryRun:
        logger.info(f"Dry run - {message}")
        logger.debug(body)
        return
    longSleep()
    requests.post(url, json.dumps(body), headers=headers, timeout=DEFAULT_TIMEOUT)


def getPrBody(prNum, user, html_url, prBody):
    return f"""## :point_right: Substitute PR for [#{prNum}]({html_url}) from @{user} :point_left:

*Please see the [original pull request #{prNum}]({html_url}) for a full history.*

### Original pull request body :point_down:
{prBody}"""


def getCommentBody(user, commentBody, html_url):
    return f"""### :point_right: Substitute comment for [original]({html_url}) from @{user} :point_left:

This comment was migrated using
[migratePullRequests.py](https://github.com/example-org/github-migration/blob/main/scripts/migratePullRequests.py)
from [KEY-32](https://jira.example.com/browse/KEY-32).

### Original comment :point_down:
{commentBody}"""


def updatePr(org, repo, prNumber, body, apiUrl=utils.GHEC_API_URL):
    url = f"{apiUrl}/repos/{org}/{repo}/pulls/{prNumber}"
    body_json = json.dumps(body)
    message = f"Updating PR {url} with {body_json}"
    logger.info(message)
    if dryRun:
        logger.info(f"Dry run - {message}")
        return
    longSleep()
    requests.patch(url, body_json, headers=headers, timeout=DEFAULT_TIMEOUT)


def createLabels(labelJson, prNum, org, repo, apiUrl=utils.GHEC_API_URL):
    message = f"Creating labels for {org}/{repo} PR {prNum}"
    logger.info(message)
    if dryRun:
        logger.info(f"Dry run - {message}")
        logger.debug(labelJson)
        return
    label = []
    for i in labelJson:
        label.append(i["name"])
    url = "{}/repos/{}/{}/issues/{}/labels".format(apiUrl, org, repo, prNum)
    payload = {"labels": label}
    logger.info(f"Setting Labels for PR {url}")
    longSleep()
    requests.post(url, json.dumps(payload), headers=headers, timeout=DEFAULT_TIMEOUT)


def creatReviewComments(
    sourceOrg,
    sourceRepo,
    destOrg,
    destRepo,
    prNum,
    sourceApiUrl=utils.GHES_API_URL,
    destApiUrl=utils.GHEC_API_URL,
):
    url = f"{sourceApiUrl}/repos/{sourceOrg}/{sourceRepo}/pulls/{prNum}/comments"
    repoReviewComments = getRepoPrComments(url, headers=sourceHeaders)
    for comments in repoReviewComments:
        payload = {
            "body": getCommentBody(
                f'{comments["user"]["login"]}_{USER_SUFFIX}',
                comments["body"],
                comments["html_url"],
            ),
            "user": f'{comments["user"]["login"]}_{USER_SUFFIX}',
            "created_at": f'{comments["created_at"]}',
            "updated_at": f'{comments["updated_at"]}',
            "commit_id": f'{comments["commit_id"]}',
            "original_commit_id": f'{comments["commit_id"]}',
            "position": f'{comments["commit_id"]}',
            "original_position": f'{comments["original_position"]}',
            "author_association": f'{comments["author_association"]}',
            "start_line": f'{comments["start_line"]}',
            "original_start_line": f'{comments["original_start_line"]}',
            "start_side": f'{comments["start_side"]}',
            "line": f'{comments["line"]}',
            "original_line": f'{comments["original_line"]}',
            "side": f'{comments["side"]}',
            "path": f'{comments["path"]}',
        }
        url = f"{destApiUrl}/repos/{destOrg}/{destRepo}/pulls/{prNum}/comments"
        createPrOrIssueObject(url, payload, headers=headers)


def createIssueComment(
    sourceOrg,
    sourceRepo,
    destOrg,
    destRepo,
    prNum,
    sourceApiUrl=utils.GHES_API_URL,
    destApiUrl=utils.GHEC_API_URL,
):
    url = f"{sourceApiUrl}/repos/{sourceOrg}/{sourceRepo}/issues/{prNum}/comments"
    repoComments = getRepoPrComments(url, headers=sourceHeaders)
    for comments in repoComments:
        payload = {
            "body": getCommentBody(
                f'{comments["user"]["login"]}_{USER_SUFFIX}',
                comments["body"],
                url,
            ),
            "user": f'{comments["user"]["login"]}_{USER_SUFFIX}',
            "created_at": f'{comments["created_at"]}',
            "updated_at": f'{comments["updated_at"]}',
        }
        url = f"{destApiUrl}/repos/{destOrg}/{destRepo}/issues/{prNum}/comments"
        createPrOrIssueObject(url, payload, headers=headers)


# BEGIN main logic of script
if dryRun:
    logger.info("Dry run: simulating PR migration")
else:
    logger.info("Starting PR migration")
try:  # noqa: C901
    for line in sys.stdin:  # noqa: C901
        if COMMENT_RE.match(line):
            continue
        (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
        logger.info(
            f"Migrating PRs from {sourceOrg}/{sourceRepo} to {destOrg}/{destRepo}"
        )

        utils.ghRateLimitSleep(sourceToken, logger, threshold=120)
        utils.ghRateLimitSleep(token, logger, instance="github.com")

        prStartNum = utils.getLatestPR(destOrg, destRepo, token, logger) + 1
        prEndNum = utils.getLatestPR(
            sourceOrg,
            sourceRepo,
            sourceToken,
            logger,
            "https://github.example.com/api/graphql",
        )
        dryRunPrIssueNum = prStartNum
        if checkClosedPrs:
            destOpenPrs = utils.getOpenPRs(destOrg, destRepo, token, logger)
            logger.info(
                f"{len(destOpenPrs)} open PRs found on {destOrg}/{destRepo}: {destOpenPrs}"
            )
            logger.info(
                f"Checking open PRs from destination to see if they are already closed on {sourceOrg}/{sourceRepo}"
            )

            for prNum in destOpenPrs:
                utils.ghRateLimitSleep(token, logger, instance="github.com")
                utils.ghRateLimitSleep(sourceToken, logger, threshold=120)
                repoPr = getRepoPrDetails(
                    sourceOrg,
                    sourceRepo,
                    prNum,
                    apiUrl=utils.GHES_API_URL,
                    headers=sourceHeaders,
                )
                if not repoPr:
                    message = f"Expected PR number {prNum} from {destOrg}/{destRepo} to be in {sourceOrg}/{sourceRepo} but it isn't (it could be an issue)"
                    logger.warning(message)
                    continue
                if repoPr["state"] != "open":
                    logger.info(
                        f"PR number {prNum} from {destOrg}/{destRepo} is {repoPr['state']} in {sourceOrg}/{sourceRepo}, so close it."
                    )
                    updatePr(destOrg, destRepo, prNum, {"state": "closed"})

        # runLoop = True
        # prNum = prStartNum
        # while runLoop:
        for prNum in range(prStartNum, prEndNum + 1):
            isIssue = False
            utils.ghRateLimitSleep(sourceToken, logger, threshold=120)
            utils.ghRateLimitSleep(token, logger, instance="github.com")
            if checkPrNum(prNum, destOrg, destRepo, apiUrl=utils.GHEC_API_URL):
                logger.warn(
                    f"PR already exists with number {prNum} in repo {destOrg}/{destRepo}, PR scanning will stop."
                )
                break

            repoPr = getRepoPrDetails(
                sourceOrg,
                sourceRepo,
                prNum,
                apiUrl=utils.GHES_API_URL,
                headers=sourceHeaders,
            )
            if not repoPr:
                logger.warning(
                    f"The PR number {prNum} isn't available (it might be an issue, testing ..."
                )
                repoPr = getRepoIssuesDetails(
                    sourceOrg,
                    sourceRepo,
                    prNum,
                    apiUrl=utils.GHES_API_URL,
                    headers=sourceHeaders,
                )
                if repoPr:
                    isIssue = True
                else:
                    logger.warning(
                        f"The issue number {prNum} isn't available breaking ..."
                    )
                    break
            PrTitle = repoPr["title"]
            PrBody = getPrBody(
                prNum,
                f"{repoPr['user']['login']}_{USER_SUFFIX}",
                repoPr["html_url"],
                repoPr["body"],
            )

            if isIssue:
                payload = {
                    "title": repoPr["title"],
                    "body": PrBody,
                    "milestone": repoPr["milestone"],
                }
                url = f"{utils.GHEC_API_URL}/repos/{destOrg}/{destRepo}/issues"
                createPrOrIssue(url, payload, prNum, headers=headers)
                if int(repoPr["comments"]) > 0:
                    createIssueComment(
                        sourceOrg,
                        sourceRepo,
                        destOrg,
                        destRepo,
                        prNum,
                        sourceApiUrl=utils.GHES_API_URL,
                        destApiUrl=utils.GHEC_API_URL,
                    )
            else:
                payload = {
                    "title": repoPr["title"],
                    "body": PrBody,
                    "head": repoPr["head"]["ref"],
                    "base": repoPr["base"]["ref"],
                    "state": "open",
                    "locked": repoPr["locked"],
                    "number": repoPr["number"],
                }
                branchExists = checkBranch(
                    repoPr["head"]["ref"], destOrg, destRepo, apiUrl=utils.GHEC_API_URL
                )
                if branchExists:
                    logger.info(f'Found branch {repoPr["head"]["ref"]}')
                elif repoPr["state"] == "open":
                    raise UnexpectedStateError(
                        f'For open PR {prNum}, expected the branch {repoPr["head"]["ref"]} to already exist. Push all branches for open PRs to {destOrg}/{destRepo} and try again.'
                    )
                else:
                    logger.info(f'Branch {repoPr["head"]["ref"]} not found, creating')
                    createBranch(
                        repoPr["head"]["ref"],
                        repoPr["base"]["sha"],
                        destOrg,
                        destRepo,
                        apiUrl=utils.GHEC_API_URL,
                    )

                if repoPr["state"] != "open":
                    logger.info(f'Creating dummy commit on {repoPr["head"]["ref"]}')
                    fileContents = f"""This is a _dummy commit_ constructed by
[migratePullRequests.py](https://github.com/example-org/github-migration/blob/main/scripts/migratePullRequests.py).

*Please see the [original pull request #{prNum}]({repoPr["html_url"]}) for a full history.*"""

                    utils.makeCommit(
                        destOrg,
                        destRepo,
                        token,
                        repoPr["head"]["ref"],
                        f'placeholder-{repoPr["head"]["ref"]}.md',
                        fileContents,
                        "Dummy commit from migratePullRequests.py for GHCM-32",
                        fileContents,
                        repoPr["base"]["sha"],
                        logger,
                        graphqlUrl="https://api.github.com/graphql",
                    )
                    longSleep()

                url = f"{utils.GHEC_API_URL}/repos/{destOrg}/{destRepo}/pulls"
                newPrNumber = createPrOrIssue(url, payload, prNum, headers=headers)
                prNumCreated += 1

                if repoPr["state"] == "open":
                    createLabels(
                        repoPr["labels"],
                        newPrNumber,
                        destRepo,
                        destOrg,
                        apiUrl=utils.GHEC_API_URL,
                    )

                    if int(repoPr["comments"]) > 0:
                        createIssueComment(
                            sourceOrg,
                            sourceRepo,
                            destOrg,
                            destRepo,
                            newPrNumber,
                            sourceApiUrl=utils.GHES_API_URL,
                            destApiUrl=utils.GHEC_API_URL,
                        )

                    if int(repoPr["review_comments"]) > 0:
                        creatReviewComments(
                            sourceOrg,
                            sourceRepo,
                            destOrg,
                            destRepo,
                            newPrNumber,
                            sourceApiUrl=utils.GHES_API_URL,
                            destApiUrl=utils.GHEC_API_URL,
                        )
                else:
                    url = "{}/repos/{}/{}/pulls/{}".format(
                        utils.GHEC_API_URL, destOrg, destRepo, newPrNumber
                    )
                    updatePr(destOrg, destRepo, newPrNumber, {"state": "closed"})
                    if not branchExists:
                        delBranch(
                            repoPr["head"]["ref"],
                            destRepo,
                            destOrg,
                            apiUrl=utils.GHEC_API_URL,
                        )
                if newPrNumber != prNum:
                    message = f"New PR number {newPrNumber} does not match expected PR {prNum} - this is introduced an anomaly."
                    raise UnexpectedStateError(message)

except Exception:
    logger.exception("Could not complete PR migration")
    exitCode = 1

    # prNum += 1
if dryRun:
    logger.info(
        f"Dry run: Finished with PR migration, {prNumCreated} PRs would have been created if run for real"
    )
else:
    logger.info(f"Finished with PR migration, {prNumCreated} PRs created")
sys.exit(exitCode)
