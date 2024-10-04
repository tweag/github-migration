#!/usr/bin/env python3
# getBuildkitePipelines.py
import csv
import logging
import re
import time

import requests
from utils import DEFAULT_TIMEOUT, assertGetenv, getLogger

logger = getLogger(logging.INFO)

token = assertGetenv("BUILDKITE_TOKEN", "Provide a Buildkite personal access token")
params = {"per_page": "100"}
headers = {
    "Authorization": f"Bearer {token}",
}
org = "example"
url = "https://api.buildkite.com/v2/organizations/{}/pipelines".format(org)


def remove_html_tags(text):
    """Remove html tags from a string"""
    clean = re.compile(r"[<>]")
    return re.sub(clean, "", text)


def getNextPage(resHeaders):
    next_url = ""
    if "Link" in resHeaders and len(resHeaders["Link"]) > 0:
        for link in resHeaders["Link"].split(", "):
            url, page_value = link.split("; ", 1)
            if page_value == 'rel="next"':
                logger.info("Next Page: {}".format(url))
                next_url = url
    return remove_html_tags(next_url)


def rateLimitCheck(resHeaders, limit=10):
    if int(resHeaders["RateLimit-Remaining"]) < limit:
        logger.info(
            "Rate limit triggered, Sleeping for {} seconds...".format(
                resHeaders["RateLimit-Reset"] + 2
            )
        )
        time.sleep(resHeaders["RateLimit-Reset"] + 2)


res = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
res.raise_for_status()

pipelines = []
pipelines.extend(res.json())
nextPageUrl = getNextPage(res.headers)

while len(nextPageUrl) > 0:
    # while nextPageUrl != "https://api.buildkite.com/v2/organizations/example/pipelines?page=3&per_page=100":
    rateLimitCheck(res.headers)
    res = requests.get(
        nextPageUrl, headers=headers, params=params, timeout=DEFAULT_TIMEOUT
    )
    pipelines.extend(res.json())
    nextPageUrl = getNextPage(res.headers)

with open("data/buildkite-pipelines.csv", "w") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["repo", "url"])
    for sub in pipelines:
        try:
            writer.writerow((sub["provider"]["settings"]["repository"], sub["url"]))
        except Exception as e:
            logger.info("Unable to add pipeline to csv: {}".format(sub))
            logger.info("Error: {}".format(e))
