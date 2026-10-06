# Shared Consumption environment

Inputs: `resource_group_name` (retained group), `name_prefix`, `location`, `tags`.
Outputs: `id`, `name`, `managed_resource_group_name`.

Owns a VNet, delegated /23 subnet and one external ACA workload-profiles
Consumption environment. It requests a deterministic platform-managed resource
group, but does not declare/import that group or its children. No dedicated
profile or paid logging workspace. Custom VNet platform networking still incurs
costs; see the [runbook](../../docs/livedocs-deployment.md).

Development uses this environment for LiveDocs now and the five business apps
in D/9. Portfolio consumes a tested immutable module tag and uses separate
names, group and state. The Azure providers/backend belong to the calling root.

Version 0.3.0 adds Storage and Key Vault subnet service endpoints for D/8.
Matching resource ACLs and runtime identities remain required. The development
root can enable this module through `enable_shared_environment` independently
of LiveDocs, retaining `module.consumption[0]` state addresses. SQL access uses
[D/7 exact ACA IPv4 rules](../../docs/development-network-access.md) because the
current SQL candidate is in a different region.
