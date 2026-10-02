# ECommerceStore.Infrastructure

Terraform infrastructure for the low-cost development deployment of the
e-commerce store. The separate portfolio deployment belongs to
[ECommerceStore.Infrastructure.Production](https://github.com/MichalBoczula/ECommerceStore.Infrastructure.Production).

## D/1 status

The manual **Destroy development environment** workflow is implemented on
`main`. No application resources are declared yet. Azure execution requires
the independent backend and OIDC integration in D/2. Full apply/destroy/reapply
and residual-cost verification belong to D/18; this initial skeleton is not
evidence of tested Azure destruction.

## Run the destroy button

1. Open **Actions → Destroy development environment → Run workflow**.
2. Select `main` and run it. This deletes development data and every resource
   owned by the development Terraform state once resources have been added.
3. Check the run summary. A failed verification is a failed workflow.

This workflow has only a manual trigger. Pushes and PRs cannot trigger it.
It cannot select portfolio state: the repository, branch, root directory,
default workspace and `ecommerce/development.tfstate` blob key are fixed.
Do not cancel a running Terraform operation or force-unlock its active lease.
If a run fails, resolve the cause and rerun; do not remove resources from state
to make verification pass. Future release workflows must not recreate a
destroyed environment automatically.

## D/2 configuration contract

Create a GitHub environment called `development` and set these **variables**
from the independent bootstrap repository's outputs. They are configuration
identifiers, not client secrets.

| Variable | Meaning |
| --- | --- |
| `AZURE_CLIENT_ID` | Persistent deployment identity client/application ID |
| `AZURE_TENANT_ID` | Microsoft Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Development subscription ID |
| `TFSTATE_RESOURCE_GROUP` | Independent bootstrap resource group |
| `TFSTATE_STORAGE_ACCOUNT` | Existing remote state account |
| `TFSTATE_CONTAINER` | Existing container reserved for development state |

OIDC federation subject:
`repo:MichalBoczula/ECommerceStore.Infrastructure:environment:development`.
Audience: `api://AzureADTokenExchange`.
Restrict the GitHub environment's deployment branches to `main`.
No required reviewer or additional approval gate is introduced by this task.

The bootstrap repository must keep its state storage, container, deployment
identity and federation outside the application state. Give the identity
`Storage Blob Data Contributor` on the development state container and `Reader`
on the state account for the final existence check. Give only the resource
management and role-assignment permissions needed by the application root.
It must have no management permission to delete bootstrap resources. If dev
and portfolio share an account, prefer distinct containers for data-plane RBAC;
their blob keys and Terraform states must also be distinct.

The application resource group is reserved as `rg-ecommerce-dev`. The bootstrap
resource group must have a different name. D/2 should confirm this naming
contract before adding any resources. No backend account or client-secret
values are committed to this repository.

## Destroy behavior

- Use Terraform `1.16.5`, matching `.terraform-version` and the root constraint.
- Initialize the remote Azure Blob backend using OIDC and Entra data-plane auth.
- Keep the default workspace, remote state locking and a five-minute lock wait.
- Use the pinned provider lock file without upgrades once providers are added
  in D/3. Commit `.terraform.lock.hcl`; this initial backend-only root has no
  provider dependencies or lock file yet.
- Generate `terraform plan -destroy`, reject create/update/replacement actions
  and planned deletes inside the bootstrap resource group, then apply that
  exact plan. No targeted deletes or shell-based Azure resource deletion.
- Keep raw Terraform logs, plan JSON and binary plan in a private temporary
  directory on the ephemeral runner; remove them on exit. They are not uploaded
  or printed into this public repository's workflow logs, including on failure.
  Failures report the phase; inspect detailed diagnostics in a secure session.
- Require an empty state, absence of `rg-ecommerce-dev`, and survival of the
  independent backend storage account before reporting success.

All future development apply workflows must use concurrency group
`terraform-development` with `cancel-in-progress: false`, the same root,
backend key, workspace, Terraform version, provider lock and module versions.
GitHub concurrency is not a FIFO queue and can replace a pending run; check the
run status. Azure Blob leases also protect state when operations start outside
GitHub. Do not use `-lock=false`.

This removes disposable application infrastructure and data, not Git commits,
published application images or the independent backend. Empty-state reruns
are allowed. A partially failed apply is cleaned up from its recorded state;
untracked resources require explicit investigation and reconciliation.

The current verification does not prove zero cost: D/18 must inspect ACA
managed resource groups, soft-deleted Key Vault/storage resources, retained
backups and other billable remnants. Future Terraform resources must be removed
using their original provider/module configuration, including credentials and
any required variable values; do not delete configuration before teardown.

## Local checks

```bash
bash -n scripts/check-destroy-config.sh scripts/destroy-development.sh
python3 -m unittest discover -s tests -v
terraform -chdir=environments/development fmt -check
terraform -chdir=environments/development init -backend=false -input=false
terraform -chdir=environments/development validate
```

Tests use fake Terraform/Azure executables and never connect to Azure. They
check scope isolation, protected bootstrap resources, exact plan application,
failure propagation, empty-state reruns and residual-resource failures.

## References

- [Terraform Azure backend and OIDC](https://developer.hashicorp.com/terraform/language/backend/azurerm)
- [Terraform destroy plans](https://developer.hashicorp.com/terraform/cli/commands/destroy)
- [GitHub manual workflow button](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
