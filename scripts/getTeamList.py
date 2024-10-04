#!/usr/bin/env python3
# getTeamList.py
import os

import requests
import utils
from utils import DEFAULT_ORG, DEFAULT_TIMEOUT, GHES_API_URL

org = os.getenv("GH_ORG", DEFAULT_ORG)
token = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a personal access token from the source GHES instance"
)
logger = utils.getLogger()

headers = utils.ghHeaders(token)
url = f"{GHES_API_URL}/orgs/{org}/teams"


res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
if res.status_code != 200:
    logger.error("Error: {}".format(res.status_code))
teams = res.json()
teamList = []
teamList.append(teams)

while "next" in res.links.keys():
    res = requests.get(
        res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
    )
    teams = res.json()
    teamList.append(teams)
ldaplisting = []
nonldaplisting = []
for sub in teamList:
    for newsub in sub:
        if "ldap_dn" in newsub:
            ldaplisting.append(newsub["name"])
        else:
            nonldaplisting.append(newsub["name"])

with open(f"TeamsLdap_{org}.txt", "w") as outfile:
    for item in ldaplisting:
        outfile.write(item + "\n")
with open(f"TeamsNoLdap_{org}.txt", "w") as outfile:
    for item in nonldaplisting:
        outfile.write(item + "\n")
