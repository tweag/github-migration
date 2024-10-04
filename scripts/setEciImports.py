#!/usr/bin/env python3
# setEciImports.py
#
# Given a migration ID and GUID, this script will migrate the users and teams for those repos appropriately.
#
#
# Usage:
#    GH_MIGRATION_GUID=xxx GH_MIGRATION_ID=xxx GH_ORG=xxx scripts/setEciImports.py

# ECI MIGRATION STEPS:
# To migrate repos using ECI follow the steps below which can also be found here https://docs.github.com/en/migrations/using-ghe-migrator/exporting-migration-data-from-github-enterprise-server
# ssh -i ~/.ssh/id_ed25519-gcp admin@github.example.com -p 122
# ghe-migrator add https://github.example.com/<org>/<repo> ghecmigration/migrate-<org>-<repo>.txt (When prompted, enter your GitHub Enterprise Server username and personal access token which should have repo and admin:org scopes)
# eval "$(awk '/^ghe-migrator/' ghecmigration/migrate-<org>-<repo>.txt | sed 's|$| --staging-path=/home/admin/ghecmigration|')
# You'll be able to find the exported archive in the ghecmigration folder, note the name, then exit the SSH session in GHES.
# From your local computer run the below command:
# scp -P 122 -i ~/.ssh/id_ed25519-gcp admin@github.example.com:/home/admin/ghecmigration/MIGRATION-GUID.tar.gz ~/Desktop
# Upload the exported archive to the ECI server, once the upload has been completed and migration has been started extract the migration ID and GUID and run this script with this to import users and team properly.
# Once this script has completed its run, upload the generated csv file and continue with the migration guidance on the webpage,

import functools as ft
import json
import re
from csv import DictWriter

import utils
from github import Auth, Github, GithubException
from python_graphql_client import GraphqlClient
from utils import USER_SUFFIX

"""
# Required Environment Variables
export GH_PAT=<The Personal Access Token from GHEC>
export GH_MIGRATION_GUID=<GUID of the ECI migration>
export GH_MIGRATION_ID=<ID of the ECI migration>
export GH_ORG=<the org that the migration was triggered for>
"""
logger = utils.getLogger()


token = utils.assertGetenv("GH_PAT", "Provide a GitHub.com personal access token")
migration_guid = utils.assertGetenv(
    "GH_MIGRATION_GUID", "Provide the GUID of the ECI migration"
)
migration_id = utils.assertGetenv(
    "GH_MIGRATION_ID", "Provide the ID of the ECI migration"
)
org = utils.assertGetenv(
    "GH_ORG", "Provide the org that the migration was triggered for"
)

auth = Auth.Token(token)
g = Github(auth=auth)
client = GraphqlClient(endpoint="https://eci.github.com/api/graphql")
csv_file = "user_conflicts_{}_{}.csv".format(org, migration_guid)


def make_get_query(migration_guid, org, after_cursor=None):
    query = """
query Organization {
    organization(login: ORG) {
        migration(guid: GUID) {
            migratableResources(first: 100 AFTER) {
                totalCount
                pageInfo {
                    endCursor
                    hasNextPage
                }
                edges {
                    node {
                        modelName
                        sourceUrl
                        targetUrl
                        state
                    }
                }
            }
        }
    }
}
"""
    repls = (
        ("AFTER", "{}".format(after_cursor)),
        ("GUID", '"{}"'.format(migration_guid)),
        ("ORG", '"{}"'.format(org)),
    )
    res = ft.reduce(lambda a, kv: a.replace(*kv), repls, query)
    return res


def get_all_users(org):
    members = []
    for member in g.get_organization(org).get_members():
        members.append(member.login)
    return members


def make_set_query(migration_id, dict):
    json_object = json.dumps(dict, indent=4)
    query = """
mutation AddImportMapping {
    addImportMapping(
        input: {
            migrationId: MIGRATION_ID
            mappings: JSONOBJECT
        }
    ) {
        migration {
            databaseId
            guid
            state
        }
    }
}
"""
    repls = ("MIGRATION_ID", '"{}"'.format(migration_id)), (
        "JSONOBJECT",
        "{}".format(json_object),
    )
    multiline_string = ft.reduce(lambda a, kv: a.replace(*kv), repls, query)
    pattern = r'(?<!\w)"(modelName|sourceUrl|targetUrl|action|MAP|SKIP|MERGE)"(?!\w)'
    res = re.sub(pattern, r"\1", multiline_string)
    return res


def map_objects(dict, migration_id):
    query = make_set_query(migration_id, dict)
    data = client.execute(
        query,
        headers={
            "Authorization": "Bearer {}".format(token),
            "Graphql-Features": "gh_migrator_import_to_dotcom",
        },
    )
    logger.info("mapped objects: {}".format(data))
    logger.info("{}".format(query))


def fetch_and_resolve_conflicts(org, migration_guid, migration_id, github_team, token):
    import_file = open(csv_file, "w")
    writer = DictWriter(import_file, fieldnames=["sourceUrl", "targetUrl"])
    writer.writeheader()
    has_next_page = True
    after_cursor = ""
    utils.ghRateLimitSleep(token, logger, instance="github.com")
    users = get_all_users(org)

    while has_next_page:
        utils.ghRateLimitSleep(token, logger, instance="github.com")
        data = client.execute(
            query=make_get_query(migration_guid, org, after_cursor),
            headers={
                "Authorization": "Bearer {}".format(token),
                "Graphql-Features": "gh_migrator_import_to_dotcom",
            },
        )
        users_to_map = []
        teams_to_merge = []
        for model in data["data"]["organization"]["migration"]["migratableResources"][
            "edges"
        ]:
            node = model["node"]
            node["action"] = node.pop("state")
            if node["modelName"] == "user":
                user_name = node["sourceUrl"].split("github.example.com/", 1)[1]
                cloud_user_name = f"{user_name}_{USER_SUFFIX}"
                node["modelName"] = "undefined"
                if cloud_user_name in users:
                    node["targetUrl"] = "https://github.com/{}".format(cloud_user_name)
                    node["action"] = "MAP"
                    csv_node = {
                        k: v for k, v in node.items() if k in ("sourceUrl", "targetUrl")
                    }
                    writer.writerow(csv_node)
                    users_to_map.append(node)
            if node["modelName"] == "team":
                node["targetUrl"] = "https://github.com/orgs/{}/teams/{}".format(
                    org, github_team
                )
                node["action"] = "MERGE"
                node["modelName"] = "undefined"
                teams_to_merge.append(node)
        if len(users_to_map) > 0:
            map_objects(users_to_map, migration_id)
        if len(teams_to_merge) > 0:
            map_objects(teams_to_merge, migration_id)

        has_next_page = data["data"]["organization"]["migration"][
            "migratableResources"
        ]["pageInfo"]["hasNextPage"]
        after_cursor = ', after: "{}"'.format(
            data["data"]["organization"]["migration"]["migratableResources"][
                "pageInfo"
            ]["endCursor"]
        )
    import_file.close()


github_team = "migration_dummy_team"
github_org = g.get_organization(org)

logger.info("Creating team - {} in org {}".format(github_team, org))
try:
    github_org.create_team(github_team, privacy="closed", permission="push")
except GithubException as e:
    logger.warning(e.args[1]["message"])

logger.info("Starting object mapping")
fetch_and_resolve_conflicts(org, migration_guid, migration_id, github_team, token)
