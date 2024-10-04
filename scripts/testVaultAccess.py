#!/usr/bin/env python3
# testVaultAccess.py
#
# Ensure that the token provided has adequate permission to read and write from
# the areas of Vault that the webhook secrets will need
#
# Adapted from https://github.com/hashicorp/vault-examples/blob/main/examples/_quick-start/python/example.py
# MPL 2.0 Licensed under https://github.com/hashicorp/vault-examples/blob/main/LICENSE
#
# Required Environment Variables:
#
#     export VAULT_TOKEN=<The Vault Token from vault.example.com>
import json
import string
import sys
from secrets import choice

import hvac
import utils

logger = utils.getLogger()

vaultToken = utils.assertGetenv("VAULT_TOKEN", "Provide a Vault token")

SECRET_LENGTH = 40
SECRET_CHARS = string.ascii_uppercase + string.ascii_lowercase + string.digits

warnings = 0

logger.info("Logging into vault")
client = hvac.Client(
    url="https://vault.example.com:8200",
    token=vaultToken,
)
for namespace in ["prod", "dev"]:
    path = "reverse-proxy/"
    mount_point = "/langplats/{}/kv/secrets".format(namespace)
    logger.info(
        "Listing secrets for {} in mountpoint {}".format(namespace, mount_point)
    )
    try:
        list_response = client.secrets.kv.v2.list_secrets(
            path=path,
            mount_point=mount_point,
        )
        logger.info(json.dumps(list_response))
    except hvac.exceptions.InvalidPath as e:
        logger.warning(e)
        logger.warning(
            "Invalid Path - no secrets found under {} in {}".format(mount_point, path)
        )
        warnings = warnings + 1

    path = "test"
    # Reading a secret - sample is only in prod now
    try:
        logger.info("Retrieving secret {}".format(path))
        read_response = client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=mount_point, raise_on_deleted_version=True
        )
        logger.info(json.dumps(read_response))
    except hvac.exceptions.InvalidPath as e:
        logger.warning(e)
        logger.warning(
            "Invalid Path - no secrets found under {} in {}".format(mount_point, path)
        )
        warnings = warnings + 1

    # Writing a secret - permission is not yet granted
    path = "reverse-proxy/testvaultaccess.invalid"
    try:
        logger.info("Writing secret {}".format(path))
        newsecret = {
            "value": "".join([choice(SECRET_CHARS) for _ in range(SECRET_LENGTH)])
        }
        create_response = client.secrets.kv.v2.create_or_update_secret(
            path=path, secret=newsecret, mount_point=mount_point
        )
        logger.info(json.dumps(create_response))
    except Exception as e:
        logger.warning(e)
        logger.warning(
            "Could not create secret under {} at {}".format(mount_point, path)
        )
        warnings = warnings + 1

if warnings > 0:
    logger.error("Checks were not all successful - check WARNING logs for details")
    sys.exit(1)
