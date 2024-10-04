#!/usr/bin/env python3
# getWebhookType.py

import csv
import socket

from IPy import IP

fields = ["hook", "IP", "IP Type"]
rows = []

with open("hooks-unique-domain-sorted.txt", "r") as hooklst:
    for line in hooklst:
        try:
            hook = line.strip()
            result = socket.gethostbyname(hook)
            ip = IP(result)
            iptype = ip.iptype()
            row = {"hook": hook, "IP": result, "IP Type": iptype}
            rows.append(row)
        except Exception:
            row = {"hook": hook, "IP": "Unable to find Hostname", "IP Type": "null"}
            rows.append(row)
            pass
with open("hooks-unique-domain-IP-map.csv", "w", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
