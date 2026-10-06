# ECommerceStore.Infrastructure

Terraform infrastructure for the low-cost development deployment of the
e-commerce store. The separate portfolio deployment belongs to
[ECommerceStore.Infrastructure.Production](https://github.com/MichalBoczula/ECommerceStore.Infrastructure.Production).

Provision and destroy Azure infrastructure from VS Code with Azure CLI and
Terraform using the [local PowerShell runbook](docs/local-development.md).
GitHub CI validates code; existing manual deployment workflows remain optional.
Local runs use the same Azure Blob state and locking, with no workstation-IP
database rule. Runbooks cover the D/6 database stage, [D/7 network access](docs/development-network-access.md)
and complete-state teardown.

## Deployment status

- **D/1:** manual destroy workflow with scope checks and teardown verification.
- **D/2:** independent state store and identity foundation configured. The
  [live backend verification](https://github.com/MichalBoczula/ECommerceStore.Infrastructure/actions/runs/37235189600)
  passed; the operator reports the lifecycle checks passed.
- **D/3:** development root, reusable naming/tag module, provider pins and
  Windows/Linux checksums, offline PR plan summaries and module version publication.

- **D/4:** shared Consumption environment and stateless LiveDocs app, manual
  saved-plan deployment, persistent private archive root and protected teardown.
  Live Azure apply/destroy/reapply evidence is still pending; follow the
  [LiveDocs setup runbook](docs/livedocs-deployment.md).

- **D/5:** reviewed immutable business image set, consumer contract evidence,
  separate Angular artifact checksum/extractor and cloud configuration inventory.
  See the [release inventory](docs/development-release.md). This does not deploy
  the business applications or complete Azure acceptance.

- **D/6:** the operator reported local creation of the SQL server/database in
  France Central and DocumentDB in North Europe on 2026-10-06. Free/network
  management-API verification remains pending. The operator reported the
  disposable deployment cleared before D/7.
  This does not establish application compatibility.
- **D/7:** [local network access](docs/development-network-access.md) implements
  independent shared-environment activation, ACA egress discovery and exact-IP
  SQL/Mongo firewall rules. Storage/Key Vault subnet endpoints prepare D/8.
  Live apply, source observation and allowed/denied connectivity remain pending.

Full application
apply/destroy/reapply and residual-cost verification belong to D/19. The
persistent foundation lives in
[ECommerceStore.TerraformState](https://github.com/MichalBoczula/ECommerceStore.TerraformState).

## Structure and versioning

`environments/development` is the application root. `modules/deployment-context`
provides reusable names and tags without Azure resources or credentials. `modules/consumption-environment` owns the VNet/subnet/shared ACA environment;
`modules/livedocs` owns the documentation host and its immutable image. The
persistent archive lives in a separate `foundations/livedocs` root/state.
Database candidates are implemented; business services and frontend remain later deployment tasks. See [module usage and versioning](modules/README.md) and the
[ADR index](docs/adr/README.md).

Terraform is pinned to `1.16.5`, AzureRM to `5.8.0` and AzAPI to `2.13.0`.
The committed root lock file includes Windows and Linux checksums. AzureRM
automatic provider registration is disabled because registration is a foundation
operator responsibility. AzAPI supplies Azure SQL Free properties and DocumentDB resources that
this AzureRM version does not expose. Database eligibility and application
compatibility still need D/6 provisioning and D/9 deployment verification; see the
[provider capability audit](docs/provider-capabilities.md).

Every PR runs credential-free Terraform validation and mock plan tests on Linux
and Windows. Linux job summaries show resource action counts and output names,
without raw plan values. These are **offline configuration previews**; they do
not inspect live Azure state or establish what a real deployment will change.
LiveDocs has a main-only manual plan/apply workflow; pushes cannot deploy it. PR jobs receive no Azure IDs,
OIDC permission or backend access.

After a merge, successful `Terraform CI` on `main` triggers **Publish module
version**, which creates `modules-v<modules/VERSION>` at the tested commit.
`modules-v0.1.0` and `modules-v0.2.0` are published. D/7 proposes `0.3.0`;
its immutable tag is published only after successful merged main CI. Existing tags are never moved. Module changes
require a version bump. Portfolio roots will consume a published tag rather
than `main`.

## One-subscription teardown contract

The user chose one Azure subscription. Bootstrap therefore owns a persistent,
empty `rg-ecommerce-dev`, deployment identity and scoped access assignments.
Application Terraform owns only disposable children. Destroy requires empty
application state and zero child application resources in the retained group.
That group stays so its scoped access works on the next deployment.

Do not declare or import the group as an application resource; future roots
should read it as data. The custom deployment role excludes group deletion and
access/lock-management writes. Management access is limited to the dev group;
the state account gets Reader only, with Blob Data Contributor only on the dev
state container. No subscription-wide deployment grant is required.
See [ADR 0001](docs/adr/0001-one-subscription-bootstrap-and-teardown.md).

## Verify D/2

After creating the independent state store outside Terraform, applying the
persistent identity foundation against that remote backend and configuring
GitHub, run **Actions → Verify development backend → Run workflow** on `main`.
It verifies OIDC authentication, remote init, locked planning, a no-change apply
and remote state read. It rejects plans with managed-resource changes; the
initial empty state is persisted without placeholder Azure resources.
All application lifecycle workflows share concurrency group `terraform-development`.

## Destroy locally or use the optional button

The normal operator path is the [local saved-plan teardown](docs/local-development.md#destroy-the-current-disposable-environment).
Keep existing flags/passwords until cleanup succeeds. Verify the empty state,
retained group and backend/archive survival before reporting completion.
The optional GitHub route is:

1. Open **Actions → Destroy development environment → Run workflow**.
2. Select `main` and run it. This deletes development data and every resource
   owned by the development Terraform state once resources have been added;
   the bootstrap-owned empty group, identity and state store remain.
3. Check the run summary. A failed verification is a failed workflow.

This workflow has only a manual trigger. Pushes and PRs cannot trigger it.
It cannot select portfolio state: the repository, branch, root directory,
default workspace, `development-state` container and
`ecommerce/development.tfstate` blob key are fixed.
Do not cancel a running Terraform operation or force-unlock its active lease.
If a run fails, resolve the cause and rerun; do not remove resources from state
to make verification pass. Future release workflows must not recreate a
destroyed environment automatically.

## D/2 configuration contract

Create a GitHub environment called `development` and add each value separately
from the foundation repository's `development_github_variables` output.
Store the three Azure IDs as **environment secrets** to keep their values
hidden and masked in workflow logs, as requested by the user. They are
identifiers rather than client passwords; Azure authentication still uses OIDC.
Store the three backend settings as **environment variables**.

| Name | GitHub location | Meaning |
| --- | --- | --- |
| `AZURE_CLIENT_ID` | Environment secrets | Persistent deployment identity client/application ID |
| `AZURE_TENANT_ID` | Environment secrets | Microsoft Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Environment secrets | Development subscription ID |
| `TFSTATE_RESOURCE_GROUP` | Environment variables | Independent state-storage resource group |
| `TFSTATE_STORAGE_ACCOUNT` | Environment variables | Existing remote state account |
| `TFSTATE_CONTAINER` | Environment variables | Exactly `development-state` |

All application lifecycle workflows read Azure IDs via `secrets` and backend settings
via `vars`. Do not paste the whole JSON into one value. If the Azure IDs were
previously added as variables, replace those entries with environment secrets.

OIDC federation subject:
`repo:MichalBoczula@38834900/ECommerceStore.Infrastructure@1401844464:environment:development`.
Audience: `api://AzureADTokenExchange`.
Restrict the GitHub environment's deployment branches to `main`.
No required reviewer or additional approval gate is introduced by this task.

The state account and containers are created once outside Terraform. The
foundation repository reads that existing account as data and manages the
persistent deployment identity, federation and access assignments in a separate
remote state. All of them remain outside the application state. Give the identity
`Storage Blob Data Contributor` on the development state container and `Reader`
on the state account for the final existence check. The custom management role
is assigned only on the retained application group. Application role-assignment
delegation stays disabled until D/8 needs specific data roles.
It must have no management permission to delete bootstrap resources. If dev
and portfolio share an account, prefer distinct containers for data-plane RBAC;
their blob keys and Terraform states must also be distinct.

The application resource group is reserved as `rg-ecommerce-dev`. The bootstrap
resource group must have a different name. D/2 should confirm this naming
contract before adding any resources. No backend account or client-secret
values are committed to this repository.

## Destroy behavior

- Use Terraform `1.16.5`, matching `.terraform-version` and the root constraint.
- Initialize the same remote Azure Blob backend using Azure CLI locally, or
  OIDC on the optional GitHub runner, with Entra data-plane auth.
- Keep the default workspace, remote state locking and a five-minute lock wait.
- Use the committed provider lock file with `-lockfile=readonly`; ordinary
  lifecycle runs must not upgrade dependencies.
- Generate `terraform plan -destroy`, reject create/update/replacement actions
  and planned deletes inside the bootstrap resource group or deletion of the
  retained application group itself, then apply that
  exact plan. No targeted deletes or shell-based Azure resource deletion.
- Keep raw Terraform logs, plan JSON and binary plan in a private temporary
  directory; remove them after local use or on runner exit. They are not uploaded
  or printed into this public repository's workflow logs, including on failure.
  Failures report the phase; inspect detailed diagnostics in a secure session.
- Require an empty state, retained `rg-ecommerce-dev` with zero child application
  resources, and survival of the
  independent backend storage account before reporting success.

All future development apply workflows must use concurrency group
`terraform-development` with `cancel-in-progress: false`, the same root,
backend/container/key, workspace, Terraform version, provider lock and module versions.
GitHub concurrency is not a FIFO queue and can replace a pending run; check the
run status. Azure Blob leases also protect state when operations start outside
GitHub. Do not use `-lock=false`.

This removes disposable application infrastructure and data, not Git commits,
published application images or the independent backend. Empty-state reruns
are allowed. A partially failed apply is cleaned up from its recorded state;
untracked resources require explicit investigation and reconciliation.

The current verification does not prove zero cost: D/19 must inspect ACA
managed resource groups, soft-deleted Key Vault/storage resources, retained
backups and other billable remnants. Future Terraform resources must be removed
using their original provider/module configuration, including credentials and
any required variable values; do not delete configuration before teardown.

## Local checks

```bash
for script in scripts/*.sh; do bash -n "$script"; done
python3 -m unittest discover -s tests -v
bash scripts/check-terraform.sh
```

Use Terraform `1.16.5` on `PATH`. These checks download pinned providers but
never authenticate to Azure. The Terraform tests check environment, naming and
tag contracts; Python tests check lifecycle isolation, summary redaction and
immutable module publication.

In Windows PowerShell, run the root checks with quoted arguments:

```powershell
terraform "-chdir=environments/development" init -backend=false -input=false -lockfile=readonly
terraform "-chdir=environments/development" validate
terraform "-chdir=environments/development" test "-test-directory=tests"
```

Optional local settings start from `development.tfvars.example`. Copy it to
`development.auto.tfvars` in the same directory; local variable and backend
files are ignored. Defaults already match the development contract.

For an intentional provider upgrade, update exact constraints, then regenerate
the lock file and review the capability audit:

```bash
terraform -chdir=environments/development init -backend=false -input=false -upgrade
terraform -chdir=environments/development providers lock -platform=linux_amd64 -platform=windows_amd64
```

D/5 records application images, ports, configuration and dependencies in
`releases/development.json`. Next: execute the local D/7 access stages;
D/9 verifies real driver compatibility and adds the
five business apps to this shared environment. LiveDocs publishes an image
only; Infrastructure owns its Azure deployment and image updates.

D/4 adds environment variables `LIVEDOCS_ENABLED=true` and
`LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT` after archive setup. No additional LiveDocs
Azure identity or secret is required. The archive root is operator-only and
never called by application deployment or destroy. The app identity has Reader
on the archive account for retention checks and no archive data access.
Custom ACA networking adds platform-managed networking charges; scale-to-zero
does not make a custom VNet deployment wholly free. See the runbook for the
manual lifecycle and residual-resource audit.

## References

- [Terraform Azure backend and OIDC](https://developer.hashicorp.com/terraform/language/backend/azurerm)
- [Terraform destroy plans](https://developer.hashicorp.com/terraform/cli/commands/destroy)
- [GitHub manual workflow button](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

LD/5 adds container-scoped CI archive identities in `foundations/livedocs`; see
[ADR-0005](docs/adr/0005-livedocs-archive-ci-identities.md). Apply a fresh foundation
plan to create them and read `products_livedocs_client_id`, `livedocs_reader_client_id`,
`livedocs_tenant_id` and `livedocs_subscription_id`. This does not deploy ACA or
change application state. The `livedocs` container and its access roles remain separate from photos;
a photos container can coexist in the same persistent account.

# D/6 database provisioning

The optional Free SQL/DocumentDB candidate is disabled by default. Use the
[local runbook](docs/local-development.md) to plan/apply and run the existing
Azure Free/network readback checker. The optional candidate workflow performs
the same policy/readback checks. Follow the [D/6 contract](docs/database-compatibility-gate.md),
then continue with D/7 networking. D/9 verifies driver compatibility from Azure,
D/17 checks the business flow, and D/19 proves recreation. PR CI provides a
native positive control; cloud compatibility remains pending deployment evidence.
All candidate resources use the existing disposable development state.
