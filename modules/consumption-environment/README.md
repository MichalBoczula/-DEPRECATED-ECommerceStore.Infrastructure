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
