#!/usr/bin/env python3
# getUserList.py

import requests
from utils import DEFAULT_TIMEOUT, GHES_API_URL, assertGetenv, getLogger, ghHeaders

logger = getLogger()
token = assertGetenv(
    "GH_SOURCE_PAT", "Provide a personal access token from the GHEC source instance"
)
headers = ghHeaders(token)
url = f"{GHES_API_URL}/users"

res = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
if res.status_code != 200:
    logger.warning(f"Error: {res.status_code}")
users = res.json()
userList = []
userList.append(users)

while "next" in res.links.keys():
    res = requests.get(
        res.links["next"]["url"], headers=headers, timeout=DEFAULT_TIMEOUT
    )
    users = res.json()
    userList.append(users)
sas = []
users = []
for sub in userList:
    for newsub in sub:
        # Thanks https://stackoverflow.com/a/73673029 for the hint on GH Bot users
        if "type" in newsub and newsub["type"] != "Bot":
            if "ldap_dn" not in newsub:
                sas.append(newsub["login"])
            else:
                users.append(newsub["login"])

with open("UsersLdap.txt", "w") as outfile:
    for item in users:
        outfile.write(item + "\n")

with open("UsersNoLdap.txt", "w") as outfile:
    for item in sas:
        outfile.write(item + "\n")
