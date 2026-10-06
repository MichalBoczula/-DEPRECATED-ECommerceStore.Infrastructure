# ADR 0006: local ACA access to Free database candidates

Status: accepted implementation approach for D/7; live access acceptance pending.
Date: 2026-10-06.

## Context

The operator created SQL in France Central after North Europe and West Europe
admission failures; DocumentDB uses North Europe. The shared ACA Consumption
module uses North Europe. SQL service-endpoint rules require a matching region.
The operator prefers VS Code PowerShell provisioning and complete-state teardown,
with GitHub used for code checks. Initial deployment excludes paid egress
appliances, private endpoints and broad database firewall rules.

## Decision

Enable the existing shared environment independently of LiveDocs. Add Storage
and Key Vault subnet service endpoints for D/8, which supplies resource-side ACLs
and identities. Retain the established Terraform state addresses and backend.

Provision networking and the existing pinned LiveDocs app first, with database
access disabled. Read Container Apps' `outboundIpAddresses` through ARM and
write only canonical public IPv4 addresses into ignored local configuration.
Enable Free databases' TLS public endpoints with exact per-IP SQL/Mongo rules.
The local saved-plan policy re-reads egress before apply, enforces Free/AutoPause
and rejects replacements or unknown/paid resources. Only obsolete firewall
rules may be deleted during refresh. Post-apply readback rejects extra rules.
LiveDocs archive existence and public source/HTTPS checks remain in the route.

D/9 extends egress discovery to every business app and runs pinned application
drivers from Azure. ARM readback and observing an egress request are separate
from authenticated connectivity, transactions and denial from an unlisted source.

## Consequences

Public endpoints are enabled only with explicit access inputs; default plans
remain closed. IP changes require rediscovery and ACL refresh. This avoids a
paid fixed-egress gateway but cannot promise stable addresses or zero networking
cost. North Europe to France Central introduces cross-region traffic/latency.
Storage/Key Vault endpoints alone do not grant access. No workstation IP or local
database driver installation is needed. All disposable resources use one state
and complete-state teardown; the persistent archive remains independent.

Runbook: [D/7 local network access](../development-network-access.md).
