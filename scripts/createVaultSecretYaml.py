#!/usr/bin/env python3
# createVaultSecretYaml.py

import pandas as pd
import utils
import yaml

"""
# Required Environment Variables
export VAULT_TOKEN=<a valid Vault Token>
"""

logger = utils.getLogger()

vaultToken = utils.assertGetenv("VAULT_TOKEN", "Provide a Vault token")
vaultHeaders = {"X-VAULT-TOKEN": f"{vaultToken}"}
vaultUri = "https://vault.example.com:8200/v1/secret/data"


def write_yaml_to_file(py_obj, filename):
    with open(
        f"{filename}.yaml",
        "w",
    ) as f:
        yaml.dump(py_obj, f, sort_keys=False)
    logger.info("Written to file successfully")


data = pd.read_csv("hooks-unique-domain-IP-map.csv")

"""
You might be wondering, why transform both PRIVATE and unknown
ips? There are some obsolete hostnames in the webhook that no longer
resolve to real hostnames, but if we treat those as public, GitHub.com
is going to try to resolve those and leak the hostnames into public DNS.

So although it is ugly to have some of these obsolete webhook domains
as secrets, it is safer.
"""
result = data.loc[data["IP Type"] != "PUBLIC", "hook"]

hostNamelist = result.tolist()
secretDataList = []


for host in hostNamelist:
    vaultPath = utils.getVaultPath(host)
    mount_point = utils.getVaultMountpoint(host)
    hmacSecret = utils.readOrCreateVaultSecret(
        logger, vaultUri, vaultHeaders, vaultPath, mount_point
    )
    vaultSecretName = vaultPath.split("/", 1)[1]

    secretData = {
        "name": vaultSecretName,
        "valueFrom": {"secretKeyRef": {"key": "latest", "name": vaultSecretName}},
    }
    secretDataList.append(secretData)

write_yaml_to_file(secretDataList, "vaultSecretObjects")
