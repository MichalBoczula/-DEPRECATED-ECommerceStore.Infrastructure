#!/usr/bin/env python3
"""Reject non-destroy actions and resources belonging to bootstrap storage."""
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    plan = json.load(source)

protected_group = "/resourcegroups/" + os.environ["TFSTATE_RESOURCE_GROUP"].lower()
deletes = 0
for resource in plan.get("resource_changes", []):
    if resource.get("mode") != "managed":
        continue
    change = resource["change"]
    actions = change["actions"]
    if actions not in (["delete"], ["no-op"]):
        sys.exit("Destroy plan rejected: unexpected managed-resource action.")
    if actions == ["delete"]:
        before = change.get("before") or {}
        resource_id = str(before.get("id", "")).lower().rstrip("/")
        if resource_id.endswith(protected_group) or protected_group + "/" in resource_id:
            sys.exit("Destroy plan rejected: bootstrap resource group must survive.")
        deletes += 1
print(deletes)
