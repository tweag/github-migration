#!/usr/bin/env python3
# migrateWebhook.py
#
# Migrate and activate the webhooks for one or more GitHub repositories that
# are now on GitHub Enterprise Cloud.
#
# Takes a list of source,destination org/repo pairs of repositories from STDIN and migrate
#
# Accepts either:
#  source,destination org/repo pairs of repositories
#  destination org/repo pair of repositories
#
# Usage:
#     scripts/migrateWebhook.py <<<"org/github-migration,example-org/github-migration"
#     scripts/migrateWebhook.py <<<"example-org/github-migration"
# or
#     scripts/migrateWebhook.py < data/repoListPairs.txt

import json
import sys
from time import sleep
from urllib.parse import urlparse

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export VAULT_TOKEN=<The Vault Token from vault.example.com>
export GH_SOURCE_PAT=<The Personal Access Token from GHES>

# Optional Environment Variables
export GH_ORG=<GHEC org name>
"""

logger = utils.getLogger()


token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
sourceToken = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a GitHub Enterprise Server personal access token"
)
vaultToken = utils.assertGetenv("VAULT_TOKEN", "Provide a Vault token")


REPLAY_DOMAINS = {
    # The origin domains were "reverse-proxy.example.com",
    # Assume replay-dev for now, hopefully Chris J
    "dev": "replay-dev.example.com",
    # Prod is now a real value
    "prod": "replay.example.com",
}

# Require HTTPS for webhook destinations
PROTO = "https"


# Secret lengths for HMAC secrets we generate

headers = {
    "Authorization": f"token {token}",
}
sourceHeaders = {
    "Authorization": f"token {sourceToken}",
}

vaultHeaders = {"X-VAULT-TOKEN": f"{vaultToken}"}
vaultUri = "https://vault.example.com:8200/v1/secret/data"


# Loop through the list of repos from STDIN
def getRepoHooks(org, repo, headers=headers, apiUrl=utils.GHEC_API_URL):
    url = "{}/repos/{}/{}/hooks".format(apiUrl, org, repo)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)

    if res.status_code == 200:
        hooks = res.json()
        return hooks
    elif res.status_code == 404:
        logger.info("No hooks found in {}".format(url))
        return {}
    else:
        logger.error(
            "Got {} error from {}, message: {}".format(res.status_code, url, res.json())
        )
        sys.exit(1)


def getHooksActiveList(
    sourceOrg, sourceRepo, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
):
    hooks = getRepoHooks(sourceOrg, sourceRepo, headers=headers, apiUrl=apiUrl)
    # search in  for active hooks
    hooksActiveList = []
    for hook in hooks:
        hookUrl = hook["config"]["url"]
        hookActive = hook["active"]

        if hookActive:
            hooksActiveList.append(hookUrl)
    return hooksActiveList


def getHooksSecretList(
    sourceOrg, sourceRepo, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
):
    hooks = getRepoHooks(sourceOrg, sourceRepo, headers=headers, apiUrl=apiUrl)
    # search in  for active hooks
    hooksSecretList = []
    for hook in hooks:
        hookUrl = hook["config"]["url"]
        if "secret" in hook["config"]:
            hooksSecretList.append(hookUrl)
    return hooksSecretList


def getHmacSecret(destOrg, destRepo, hookDomain):
    mount_point = utils.getVaultMountpoint(hookDomain)
    vaultPath = utils.getVaultPath(hookDomain)
    # Try reading an existing secret for hook domain, create if not found

    hmacSecret = utils.readOrCreateVaultSecret(
        logger, vaultUri, vaultHeaders, vaultPath, mount_point
    )
    return hmacSecret


def patchWebhook(
    destOrg,
    destRepo,
    hookUrl,
    hookContentType,
    hookDomain,
    hooksActiveList,
    hooksSecretList,
    apiUrl=utils.GHEC_API_URL,
    headers=headers,
):
    destApiHookUrl = "{}/repos/{}/{}/hooks/{}".format(apiUrl, destOrg, destRepo, hookId)
    if (
        utils.isIpPrivate(hookDomain, logger)
        and hookDomain not in utils.PUBLIC_HOOK_DOMAIN_WITH_SECRET
    ):
        hmacSecret = getHmacSecret(destOrg, destRepo, hookDomain)

        logger.info(
            "Patching webhook URL {} to set HMAC secret for {} for the ultimate destination domain {}".format(
                destApiHookUrl, hookUrl, hookDomain
            )
        )
        payload = {
            "config": {
                "secret": hmacSecret,
                "content_type": hookContentType,
                "url": hookUrl,
            }
        }
        sleep(1)
        utils.ghRateLimitSleep(token, logger, instance="github.com")
        res = requests.patch(
            destApiHookUrl,
            json.dumps(payload),
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        if res.status_code == 200:
            logger.info(
                "Patched webhook URL {} to set HMAC secret for {} for the ultimate destination domain {}".format(
                    destApiHookUrl, hookUrl, hookDomain
                )
            )
        elif res.status_code == 404:
            logger.error("No repo found at {}".format(destApiHookUrl))
            sys.exit(1)
        else:
            logger.error(
                "{} Error occurred, message {}".format(res.status_code, res.json())
            )
            sys.exit(1)

        # The first time we process a private hook domain, we have to encode it
        # with the replay service.
        if urlparse(hookUrl).netloc not in REPLAY_DOMAINS.values():
            urlPath, urlScheme = utils.edit_scheme(hookUrl)
            if hookDomain in utils.DEV_HOOK_DESTINATIONS:
                targetEnv = "dev"
            else:
                targetEnv = "prod"
            destHookUrl = "{}://{}/reverse-proxy/path/{}/{}".format(
                PROTO, REPLAY_DOMAINS[targetEnv], urlScheme, urlPath
            )
            logger.info(
                "Using reverse proxy hook url {} for {} in {}/{}".format(
                    destHookUrl,
                    hookUrl,
                    destOrg,
                    destRepo,
                )
            )
            # Enforce SSL verification on new webhooks
            payload = {
                "config": {
                    "url": destHookUrl,
                    "insecure_ssl": 0,
                    "content_type": hookContentType,
                    "secret": hmacSecret,
                }
            }
            sleep(1)
            utils.ghRateLimitSleep(token, logger, instance="github.com")
            requests.patch(
                destApiHookUrl,
                json.dumps(payload),
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )
    elif (
        hookUrl in hooksSecretList
        and hookDomain in utils.PUBLIC_HOOK_DOMAIN_WITH_SECRET
    ):
        # If hook URL has a public domain which also has secrets, migrate those secrets across
        destHookUrl = hookUrl
        mount_point = utils.getVaultMountpoint(hookDomain)
        vaultPath = utils.getVaultPath(hookDomain)
        hmacSecret = utils.readOrCreateVaultSecret(
            logger, vaultUri, vaultHeaders, vaultPath, mount_point
        )
        logger.info(
            "Adding secret for public IP webhook {} in repo {}/{}".format(
                destHookUrl, destOrg, destRepo
            )
        )
        payload = {
            "config": {
                "url": hookUrl,
                "insecure_ssl": 0,
                "content_type": hookContentType,
                "secret": hmacSecret,
            }
        }
        sleep(1)
        utils.ghRateLimitSleep(token, logger, instance="github.com")
        requests.patch(
            destApiHookUrl,
            json.dumps(payload),
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
    else:
        # If hook URL domain has a public IP address, the destination URL
        # remains the same.,
        destHookUrl = hookUrl
    if hookUrl in hooksActiveList:
        logger.info(
            f"marking as active hook: {destHookUrl} in repo: {destOrg}/{destRepo}"
        )
        payload = {"active": True}
        sleep(1)
        utils.ghRateLimitSleep(token, logger, instance="github.com")
        requests.patch(
            destApiHookUrl,
            json.dumps(payload),
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )


# BEGIN main logic of script
for line in sys.stdin:  # noqa: C901
    if COMMENT_RE.match(line):
        continue
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    repoDetails = utils.getRepoDetails(
        logger, destOrg, destRepo, headers=headers, apiUrl=utils.GHEC_API_URL
    )
    archived = repoDetails["archived"]
    if archived:
        logger.warning("Skipping {} as it is archived".format(line))
        continue

    hooksActiveList = getHooksActiveList(
        sourceOrg, sourceRepo, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
    )
    hooksSecretList = getHooksSecretList(
        sourceOrg, sourceRepo, headers=sourceHeaders, apiUrl=utils.GHES_API_URL
    )

    # Get webhooks in GHEC
    hooks = getRepoHooks(destOrg, destRepo, headers=headers, apiUrl=utils.GHEC_API_URL)

    for hook in hooks:
        logger.debug("processing hook {}".format(hook))
        hookUrl = hook["config"]["url"]
        hookContentType = hook["config"]["content_type"]
        hookId = hook["id"]
        # the hookDomain is either the main domain in the webook,
        # or we have to crack it out of the path if the webhook uses one of
        # the reverse proxy domains.
        hookUrlParsed = urlparse(hookUrl)
        origHookDomain = hookUrlParsed.netloc
        if origHookDomain in REPLAY_DOMAINS.values():
            hookUrlList = hookUrl.split("/", -1)
            if hookUrlList[4] == "replay_path":
                hookUrl = "{}://{}".format(hookUrlList[5], "/".join(hookUrlList[6:]))
                hookDomain = urlparse(hookUrl).netloc
            else:
                logger.warning(
                    "the hook url {} isnt in a familiar format, skipping this hook".format(
                        hookUrl
                    )
                )
                continue
        else:
            hookDomain = origHookDomain
        if hookDomain in utils.OLD_TO_NEW_WEBHOOK_HOSTNAME_MAP.keys():
            newhookDomain = utils.OLD_TO_NEW_WEBHOOK_HOSTNAME_MAP[hookDomain]
            hookUrl = urlparse(hookUrl)._replace(netloc=newhookDomain).geturl()
            hooksActiveListMod = [
                sub.replace(hookDomain, newhookDomain) for sub in hooksActiveList
            ]
            hooksSecretListMod = [
                sub.replace(hookDomain, newhookDomain) for sub in hooksSecretList
            ]
            hookDomain = newhookDomain
        elif hookDomain in utils.OLD_TO_NEW_WEBHOOK_HOSTNAME_MAP.values():
            oldhookDomain = [
                k
                for k, v in utils.OLD_TO_NEW_WEBHOOK_HOSTNAME_MAP.items()
                if v == hookDomain
            ]
            hooksActiveListMod = [
                sub.replace(oldhookDomain[0], hookDomain) for sub in hooksActiveList
            ]
            hooksSecretListMod = [
                sub.replace(oldhookDomain[0], hookDomain) for sub in hooksSecretList
            ]
        else:
            hooksActiveListMod = hooksActiveList
            hooksSecretListMod = hooksActiveList

        patchWebhook(
            destOrg,
            destRepo,
            hookUrl,
            hookContentType,
            hookDomain,
            hooksActiveListMod,
            hooksSecretListMod,
        )
