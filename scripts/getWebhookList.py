#!/usr/bin/env python3
# getWebhookList.py
#
# Retrieve webhooks for active (non-archived) repos,
# scan for active webhooks,
# and emit multiple lists useful for migration

import json
import os
import sys
from collections import defaultdict
from urllib.parse import urlparse

import requests
from utils import DEFAULT_TIMEOUT, assertGetenv, getLogger, ghRateLimitSleep, DEFAULT_ORG

token = assertGetenv(
    "GH_SOURCE_PAT", "Provide a personal access token from the source GHES instance"
)
org = os.getenv("GH_ORG", DEFAULT_ORG)

headers = {
    "Authorization": f"token {token}",
}

repoUrl = "https://github.example.com/api/v3/orgs/{}/repos".format(org)

logger = getLogger()
ghRateLimitSleep(token, logger)
res = requests.get(repoUrl, headers=headers, timeout=DEFAULT_TIMEOUT)
repos = res.json()
repoList = []
repoList.append(repos)

while "next" in res.links.keys():
    ghRateLimitSleep(token, logger)
    res = requests.get(
        res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
    )
    repos = res.json()
    repoList.append(repos)

repos_active = []
repos_archived = []
for sub in repoList:
    for newsub in sub:
        if newsub["archived"]:
            repos_archived.append(newsub["name"])
        else:
            repos_active.append(newsub["name"])

hookMaps = defaultdict(list)
hookSet = set()
hookSecretSet = set()
hookMapsSecrets = defaultdict(list)
for repo in repos_active:
    url = "https://github.example.com/api/v3/repos/{}/{}/hooks".format(org, repo)
    ghRateLimitSleep(token, logger)
    res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    if res.status_code != 200:
        logger.error("Status {} getting {}".format(res.status_code, url))
        sys.exit(1)
    hooks = res.json()
    for hook in hooks:
        if hook["active"]:
            hookUrl = hook["config"]["url"]
            hookDomain = urlparse(hookUrl).netloc
            hookMaps[repo].append(hookUrl)
            hookSet.add(hookDomain)
            if "secret" in hook["config"]:
                hookMapsSecrets[repo].append(hookUrl)
                hookSecretSet.add(hookDomain)

hookMapsJsonObject = json.dumps(hookMaps, indent=4)
hookMapsSecretsJsonObject = json.dumps(hookMapsSecrets, indent=4)

with open(f"hooksRepoMap_{org}.json", "w") as outfile:
    outfile.write(hookMapsJsonObject)

with open(f"hooksOrgUniquelist_{org}.txt", "w") as outfile:
    for item in sorted(hookSet):
        outfile.write(item + "\n")

with open(f"hooksWithSecretMap_{org}.json", "w") as outfile:
    outfile.write(hookMapsSecretsJsonObject)

with open(f"hooksWithSecretUnique_{org}.txt", "w") as outfile:
    for item in sorted(hookSecretSet):
        outfile.write(item + "\n")

with open(f"repos_active_{org}.txt", "w") as outfile:
    for item in sorted(repos_active):
        outfile.write("{}/{}\n".format(org, item))

with open(f"repos_archived_{org}.txt", "w") as outfile:
    for item in sorted(repos_archived):
        outfile.write("{}/{}\n".format(org, item))
