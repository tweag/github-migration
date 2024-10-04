#!/usr/bin/env python3
# deleteAndPurgeVaultSecret.py
#
# Permanently delete a secret in Vault, purging its metadata
#
# example:
"""
scripts/deleteAndPurgeVaultSecret.py \
    --mount_point="some/mount/point" \
    "some-secret"
"""
import argparse

import hvac
import utils

vaultUrl = "https://vault.example.com:8200"

logger = utils.getLogger()

parser = argparse.ArgumentParser()
parser.add_argument("secret", help="Path to secret in vault")
parser.add_argument("--mount_point", help="Mount point for vault")
parser.add_argument(
    "--vault_token",
    help="Vault token. Specify or set VAULT_TOKEN environment variable.",
)
parser.add_argument("--verbose", help="increase output verbosity", action="store_true")
args = parser.parse_args()

if args.vault_token:
    vaultToken = args.vault_token
else:
    vaultToken = utils.assertGetenv(
        "VAULT_TOKEN", "Specify a Vault token. See scripts/getVaultToken.sh"
    )

client = hvac.Client(
    url=vaultUrl,
    token=vaultToken,
)


res = client.secrets.kv.delete_metadata_and_all_versions(
    args.secret, mount_point=args.mount_point
)

logger.info(res)
