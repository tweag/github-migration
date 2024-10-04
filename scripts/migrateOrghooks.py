#!/usr/bin/env python3
# migrateOrgHooks.py

import ipaddress
import json
import socket
import sys
from urllib.parse import urlparse

import requests
import utils
from utils import DEFAULT_TIMEOUT, GHEC_API_URL, GHEC_PREFIX

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export VAULT_TOKEN=<The Vault Token from vault.example.com>
export GH_SOURCE_PAT=<The Personal Access Token from GHES>
"""

logger = utils.getLogger()


token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
sourceToken = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a GitHub Enterprise Server personal access token"
)
vaultToken = utils.assertGetenv("VAULT_TOKEN", "Provide a Vault token")


REPLAY_DOMAINS = {
    "dev": "replay-dev.example.com",
    # Prod is now a real value
    "prod": "replay.app.example.com",
}

# Require HTTPS for webhook destinations
PROTO = "https"

# TODO put in list of real prod domains to differentiate.
# Consider reading it in from a text file instead of hardcoding it here.
DEV_HOOK_DESTINATIONS = ["somedomain.subdomain.example.com"]
# Secret lengths for HMAC secrets we generate

headers = {
    "Authorization": f"token {token}",
}
sourceHeaders = {
    "Authorization": f"token {sourceToken}",
}
vaultHeaders = {"X-VAULT-TOKEN": f"{vaultToken}"}
vaultUri = "https://vault.example.com:8200/v1/secret/data"

orgUrl = "{}/organizations".format(utils.GHEC_API_URL)

res = requests.get(orgUrl, headers=sourceHeaders, timeout=DEFAULT_TIMEOUT)
if res.status_code == 200:
    orgs = res.json()
elif res.status_code == 404:
    logger.warning("No orgs found in {}".format(orgUrl))
else:
    logger.error("Error: {} {}".format(res.status_code, res.text))
    sys.exit(1)
orgList = []
orgList.append(orgs)
orgListing = []
for sub in orgList:
    for newsub in sub:
        orgListing.append(newsub["login"])

for org in orgListing:  # noqa: C901
    ghesurl = "{}/orgs/{}/hooks".format(utils.GHEC_API_URL, org)
    res = requests.get(ghesurl, headers=sourceHeaders, timeout=DEFAULT_TIMEOUT)
    if res.status_code != 200:
        logger.error(
            "Error retrieving orgs from GHES: {} {}".format(res.status_code, res.text)
        )
        sys.exit(1)
    hooks = res.json()
    for hook in hooks:
        hookContentType = hook["config"]["content_type"]
        hookUrl = hook["config"]["url"]
        # TODO: You can swap hook urls here if needed
        hookName = hook["name"]
        hookActive = hook["active"]
        hookEvents = hook["events"]
        hookUrlParsed = urlparse(hookUrl)
        origHookDomain = hookUrlParsed.netloc
        if origHookDomain in DEV_HOOK_DESTINATIONS:
            namespace = "dev"
        else:
            namespace = "prod"

        if origHookDomain in REPLAY_DOMAINS.values():
            hookUrlList = hookUrl.split("/", -1)
            if hookUrlList[4] == "path":
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

        urlPath, urlScheme = utils.edit_scheme(hookUrl)
        destHookUrl = f"{PROTO}://{REPLAY_DOMAINS[namespace]}/reverse_proxy/path/{urlScheme}/{urlPath}"

        try:
            ip = socket.gethostbyname(hookDomain)
            isIpPrivate = ipaddress.ip_address(ip).is_private
        except socket.gaierror as err:
            isIpPrivate = True
            logger.info(
                "IP of {} is not resolvable, assigning as Private. Resolver message: {}".format(
                    hookDomain, err
                )
            )
        hookDomainVault = hookDomain.replace(".", "_").upper()
        vaultPath = "reverse-proxy/EXAMPLE_SECRET_{}".format(hookDomainVault)
        mount_point = "department/{}/kv/secrets".format(namespace)
        if isIpPrivate:
            hmacSecret = utils.readOrCreateVaultSecret(
                logger, vaultUri, vaultHeaders, vaultPath, mount_point
            )
        else:
            hmacSecret = ""
        logger.info("migrating hook: {} in org {}".format(hookUrl, org))
        payload = {
            "name": hookName,
            "active": hookActive,
            "events": hookEvents,
            "config": {
                "content_type": hookContentType,
                "insecure_ssl": "0",
                "url": destHookUrl,
                "secret": hmacSecret,
            },
        }
        requests.post(
            f"{GHEC_API_URL}/orgs/{GHEC_PREFIX}-{org}/hooks",
            json.dumps(payload),
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
