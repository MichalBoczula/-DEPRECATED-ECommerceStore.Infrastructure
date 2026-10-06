# D/7: database and storage access preparation

Status: access design prepared on 2026-10-06; Terraform implementation and live
verification remain pending. Execute provisioning locally using the
[PowerShell lifecycle runbook](local-development.md). Keep the environment
destroyed between development sessions.

## Known deployment constraints

The operator reported successful creation of SQL in **France Central** and
DocumentDB in **North Europe**. The existing Consumption environment module
uses North Europe. North Europe SQL creation was restricted; West Europe
rejected new-customer admission. France Central is the observed successful
region, not a promise of permanent eligibility. Free readback and teardown
verification have not yet been supplied.

SQL virtual-network/service-endpoint rules require the subnet and database to
be in the same region. Consequently the current North Europe ACA subnet cannot
use that route to France Central SQL. Evaluate its public TLS endpoint with
explicit ACA outbound-IP firewall rules for this split. Do not add an unusable
SQL subnet rule or infer that `public_network_access_enabled=false` allows
service endpoints. Data access is still disabled in the current D/6 root.

DocumentDB supports public firewall rules for individual IPv4 addresses. ACA
outbound public IPs may change, and the environment's inbound IP is not an
egress identity. A no-NAT design must discover actual egress and refresh the
Terraform-owned firewall rules when it changes. Live connection checks must
allow for firewall propagation, which Microsoft documents as up to 15 minutes.
Do not enable broad "allow Azure services" or all-address rules implicitly.

## Implementation order

1. Reuse the existing shared VNet/subnet/Consumption module; enable it
   independently of the LiveDocs flag while retaining existing state addresses.
   Add supported
   Storage/Key Vault service endpoints as D/8 introduces those resources;
   require their matching service-side network ACLs and runtime identity roles.
2. Provision the shared ACA environment locally with database data access still
   disabled. Read its actual egress configuration through supported Azure APIs
   and confirm the source with a bounded Azure-side network probe. Do not use
   the workstation IP or invent a fixed egress address.
3. Supply the observed addresses as local ignored configuration. Add only
   Terraform-owned SQL and Mongo IPv4 firewall rules and enable the necessary
   public endpoints. Extend saved-plan policy for these exact network changes;
   keep Free tiers/AutoPause and teardown ownership enforced.
4. On every recreate or egress change, rediscover addresses, plan/apply the ACL
   update, and remove obsolete rules. A connectivity failure starts with this
   check; it never triggers an automatic paid upgrade or broad firewall rule.
5. Prove allowed ACA access and denial from an unlisted source. D/9 separately
   runs the pinned driver/readiness/transaction suites and implements business
   app ingress: BFF public, four upstream APIs internal, LiveDocs public docs.

Until this path is proven, D/7 stays pending. No firewall or public-access
settings change merely because the design is documented. No Private Link, NAT,
paid gateway, second environment or workstation driver installation is added.
Cross-region latency/traffic costs and custom ACA networking charges belong in
the measured cost report. Moving all resources to France Central is a separate
region-policy change requiring eligibility, module/policy updates and testing.

Primary references checked 2026-10-06:

- [SQL service-endpoint regional limits](https://learn.microsoft.com/en-us/azure/azure-sql/database/vnet-service-endpoint-rule-overview?view=azuresql)
- [Container Apps outbound-IP behavior](https://learn.microsoft.com/en-us/azure/container-apps/networking#ports-and-ip-addresses)
- [DocumentDB firewall rules and propagation](https://learn.microsoft.com/en-us/azure/documentdb/how-to-configure-firewall)
