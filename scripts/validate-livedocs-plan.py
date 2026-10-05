"""Only the four D/4 disposable resources may be created or updated."""
import json
import sys

ALLOWED = {"azurerm_virtual_network", "azurerm_subnet", "azurerm_container_app_environment", "azurerm_container_app"}
ADDRESSES = {
    "module.consumption[0].azurerm_virtual_network.host": "azurerm_virtual_network",
    "module.consumption[0].azurerm_subnet.host": "azurerm_subnet",
    "module.consumption[0].azurerm_container_app_environment.host": "azurerm_container_app_environment",
    "module.livedocs[0].azurerm_container_app.host": "azurerm_container_app",
}
def validate(plan):
    counts={"create":0,"update":0}
    seen=set()
    if plan.get("errored") or plan.get("complete") is False:
        raise ValueError("D/4 plan is incomplete.")
    for item in plan.get("resource_changes",[]):
        if item.get("mode") != "managed": continue
        action=item["change"]["actions"]
        address=item.get("address")
        if (ADDRESSES.get(address) != item["type"] or address in seen
                or action not in (["create"],["update"],["no-op"])):
            raise ValueError("D/4 plan contains an unsupported change.")
        seen.add(address)
        after=item["change"].get("after") or {}
        if after.get("resource_group_name") != "rg-ecommerce-dev":
            raise ValueError("D/4 resources must use the retained application group.")
        if item["type"] == "azurerm_container_app":
            container=after["template"][0]["container"][0]
            template=after["template"][0]
            if (container["cpu"] != 0.25 or container["memory"] != "0.5Gi"
                    or template["min_replicas"] != 0 or template["max_replicas"] != 1
                    or after["workload_profile_name"] != "Consumption"
                    or after["ingress"][0]["allow_insecure_connections"]
                    or not after["ingress"][0]["external_enabled"]
                    or after["ingress"][0]["target_port"] != 8080
                    or len(template["container"]) != 1
                    or after["revision_mode"] != "Single"):
                raise ValueError("D/4 host allocation or HTTPS contract changed.")
        if item["type"] == "azurerm_container_app_environment":
            profiles=after["workload_profile"]
            if (len(profiles) != 1 or profiles[0]["workload_profile_type"] != "Consumption"
                    or profiles[0]["name"] != "Consumption" or after.get("logs_destination") is not None
                    or after.get("infrastructure_resource_group_name") != "rg-ecommerce-dev-aca-managed"):
                raise ValueError("Paid profile/logging must not enter the D/4 plan.")
        if action != ["no-op"]: counts[action[0]]+=1
    if seen != set(ADDRESSES):
        raise ValueError("The complete D/4 resource set must be present.")
    return counts
if __name__ == "__main__":
    try:
        with open(sys.argv[1]) as source: result=validate(json.load(source))
        print(f"Reviewed D/4 plan: {result['create']} creations, {result['update']} updates; no deletes or replacements.")
    except Exception:
        raise SystemExit("D/4 plan rejected; inspect private diagnostics securely.")
