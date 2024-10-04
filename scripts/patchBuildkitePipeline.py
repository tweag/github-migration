#!/usr/bin/env python3
# patchBuildkitePipeln/ine.py
#
# Update Buildkite pipeline URLs to github.com equivalents of github.example.com.
# Takes a list of source,destination org/repo pairs of repositories from STDIN and migrate
#
# Accepts either:
#  source,destination org/repo pairs of repositories
#  destination org/repo pair of repositories
# Documentation: https://docs.google.com/document/d/1ZjmbuGMxdjRf-ca-ttjtkAJV8Xy_EP1ytw1vmjY-gZ4/edit
#
# Requires BUILDKITE_TOKEN to be set, with the following scopes:
#
# "scopes": [
#        "read_agents",
#        "read_clusters",
#        "read_teams",
#        "read_builds",
#        "read_job_env",
#        "read_build_logs",
#        "read_organizations",
#        "read_pipelines",
#        "write_pipelines",
#        "read_pipeline_templates",
#        "read_user",
#        "read_suites"
#    ]
#
# Test case (this is safe):
# Set the URL in  https://buildkite.com/example/dummytest/settings/repository to
#     git@github.example.com:org/dummytest
# Then run the script
#     echo "example-org/dummytest" | scripts/patchBuildKitePipeline.py
# Then check https://buildkite.com/example/dummytest/settings/repository to see that it has worked
# Expect:
#     git@github.com:example-org/dummytest


import csv
import json
import os
import sys
from collections import defaultdict

import requests
import utils
from utils import COMMENT_RE, DEFAULT_TIMEOUT, GHEC_PREFIX, GHEC_SANDBOX_ORG

"""
# Required Environment Variables
export BUILDKITE_TOKEN=<The Buildkite Personal Access Token>
export GH_PAT=<The Personal Access Token from GHEC>
# Optional Environment Variables
export GH_ORG=<GHEC org name>
"""

dir = os.path.dirname(os.path.abspath(__file__))

logger = utils.getLogger()

token = utils.assertGetenv(
    "BUILDKITE_TOKEN", "Provide a Buildkite personal access token"
)
ghToken = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
apiPipelineEndpointBase = "https://api.buildkite.com/v2/organizations/example/pipelines"
gh_org = os.getenv("GH_ORG")

headers = {
    "Authorization": f"Bearer {token}",
}
ghHeaders = utils.ghHeaders(ghToken)


def patchBuildkitePipeline(repo, org, url, headers=headers):
    payload = {"repository": f"git@github.com:{org}/{repo}.git"}
    logger.info(
        f"patching buildite pipeline for repo https://github.com/{org}/{repo} at {url}"
    )
    res = requests.patch(
        url, json.dumps(payload), headers=headers, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code == 200:
        logger.info(f"Response for patching {url}: {res.status_code} OK")
    else:
        logger.warn(
            f"Response for patching {url}: {res.status_code} (repo https://github.com/{org}/{repo})"
        )
    return res


def get_pipeline_map():
    pipeline_map = defaultdict(list)
    with open(f"{dir}/../data/buildkite-pipelines.csv", "rt") as infile:
        reader = csv.DictReader(infile)
        for line in reader:
            pipeline_map[line["repo"]].append(line["url"])
        logger.debug("completed loading into dict")
    return pipeline_map


# BEGIN main logic of script
pipeline_map = get_pipeline_map()


# Loop through the list of repos from STDIN
for line in sys.stdin:
    if COMMENT_RE.match(line):
        continue
    (sourceOrg, sourceRepo, destOrg, destRepo) = utils.getOrgAndRepoPairs(line)
    repoDetails = utils.getRepoDetails(
        logger, destOrg, destRepo, headers=ghHeaders, apiUrl=utils.GHEC_API_URL
    )
    archived = repoDetails["archived"]
    if archived or gh_org == "{GHEC_PREFIX}-{GHEC_SANDBOX_ORG}":
        logger.warning(
            f"Skipping {line} as it is archived or the destination is {GHEC_PREFIX}-{GHEC_SANDBOX_ORG}"
        )
        continue
    if "{}/{}".format(sourceOrg, sourceRepo) in pipeline_map.keys():
        logger.info(f"Found repo {sourceOrg}/{sourceRepo} match in csv")
        apiPipelineEndpoint = pipeline_map[f"{sourceOrg}/{sourceRepo}"]
    else:
        logger.info(f"Could not find repo {sourceOrg}/{sourceRepo} in csv")
        apiPipelineEndpoint = ["{}/{}".format(apiPipelineEndpointBase, sourceRepo)]
    for endpoint in apiPipelineEndpoint:
        patchBuildkitePipeline(destRepo, destOrg, endpoint, headers=headers)
