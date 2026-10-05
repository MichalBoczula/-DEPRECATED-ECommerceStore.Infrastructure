# D/4: LiveDocs development setup

Infrastructure owns the shared ACA environment, LiveDocs host, selected image
and Azure lifecycle. LiveDocs CI builds, tests, scans and publishes an image;
it never logs in to Azure or changes a revision. No cross-repository Azure
workflow or delivery identity is required. Application lifecycle jobs share
`terraform-development` concurrency and the same leased development state.

This PR implements configuration and offline checks. **Live Azure lifecycle
verification is pending.** The commands below are operator steps after merge;
no Azure resources have been deployed by these PR checks.

## Prerequisites

Merge this Infrastructure PR after CI passes. LiveDocs PR #3 documents the
image-only contract. The initial release deliberately uses an already published
main image, source `a11d396ad01f1324569c69483e870fa8b9c23cf7`, from successful
[publication run 37064030047](https://github.com/MichalBoczula/ECommerceStore.LiveDocs/actions/runs/37064030047).
It does not claim PR #3's image was already published. A later update consumes
that PR's successful main publication metadata.

D/2's three Azure ID secrets and three backend variables remain unchanged.
Use the existing TerraformState deployment identity's **principal/object ID**,
not its client ID. Read it from the applied TerraformState repository:

```powershell
# In your initialized ECommerceStore.TerraformState checkout:
terraform output -raw development_principal_id
```

Or query the existing identity in Azure Portal.
The operator needs resource management and role-assignment privileges for the
archive root and Blob Data Contributor on the independent state store.

Use Terraform 1.16.5, Azure CLI, Git Bash and optionally GitHub CLI. Ensure
`terraform` and `az` resolve in the Bash terminal as well as PowerShell.

## One-time persistent archive setup

In PowerShell, authenticate and select the same development subscription:

```powershell
az login
az account set --subscription "YOUR_SUBSCRIPTION_ID"
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.Network --wait
az provider register --namespace Microsoft.Storage --wait
```

Clone/pull Infrastructure, then run from its repository root:

```powershell
bash scripts/init-livedocs-archive.sh "YOUR_STATE_RESOURCE_GROUP" "YOUR_EXISTING_STATE_ACCOUNT" "INFRASTRUCTURE_PRINCIPAL_ID"
terraform "-chdir=foundations/livedocs" validate
terraform "-chdir=foundations/livedocs" test "-test-directory=tests"
terraform "-chdir=foundations/livedocs" plan "-out=archive.tfplan"
terraform "-chdir=foundations/livedocs" apply "archive.tfplan"
terraform "-chdir=foundations/livedocs" output -raw archive_storage_account
```

The helper creates only a private **state container outside Terraform**:
`livedocs-archive-state`, key `ecommerce/livedocs-archive.tfstate`, in the existing
external state account. It writes ignored backend/variable files without keys
or SAS, initializes using the operator's Azure CLI session, and refuses to
overwrite a configured root. It never creates or imports the state account.
If CI/local checks already initialized `.terraform` with `-backend=false`,
remove only that provider cache before first setup; do not remove existing
backend settings or state. An existing configured checkout instead uses:

```powershell
terraform "-chdir=foundations/livedocs" init -input=false -lockfile=readonly "-backend-config=backend.hcl"
```

Terraform creates `rg-ecommerce-livedocs-archive`, a Standard LRS account,
private `livedocs` container, Entra-based storage, retained versions, 30-day
blob/container deletion retention and a CanNotDelete lock. The application
identity gets **Reader on that account only** for retention verification. The
operator gets archive Blob Data Contributor; LD/5 adds separate Products writer and LiveDocs reader identities scoped to the
private `livedocs` container. See the [integration setup](https://github.com/MichalBoczula/ECommerceStore.LiveDocs/blob/main/docs/producer-integration.md). The public host has
no archive identity or runtime blob mount. Archive data is pre-baked into images
by CI archive integration.

If Azure reports a new role is not yet effective, allow propagation then create
and review a fresh plan; do not reuse a stale saved plan or enable account keys.
Keep archive configuration/state. Its `prevent_destroy` resources and lock are
intentional. It is never included in the one-button application destroy.

## Configure the development environment

Set these **variables** under GitHub Settings → Environments → development:

| Variable | Value |
| --- | --- |
| `LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT` | The archive output above |
| `LIVEDOCS_ENABLED` | `true` |

Do not change the existing ID **secrets** or backend variables. With GitHub CLI
already authenticated, the helper sets only these two variables:

```powershell
bash scripts/configure-livedocs-development.sh
```

The enable flag keeps the backend verification/root configuration consistent
once LiveDocs exists. It is not an automatic deployment switch. After destroy,
backend verification with this flag still enabled correctly rejects the create
plan; use the explicit deploy workflow to re-create the host.

## Manual deploy and teardown

1. Actions → **Deploy LiveDocs development** → main → `plan`. Review the
   sanitized count summary: initially four creations, zero updates, no deletes
   or replacements. Raw plan JSON, state and logs are never published.
2. Run the same workflow with `apply`. It creates and checks a **fresh plan**,
   applies exactly that saved plan, and verifies HTTPS liveness/readiness,
   `/livedoc/`, CSS and `/build-info.json` matching the release's source SHA.
   The summary contains the public portal URL.
3. Open the URL and verify expected empty/available documentation content.
   Actual Products report integration belongs to LiveDocs LD/5; unavailable
   production inputs must not be silently replaced with fixtures.
4. Actions → **Destroy development environment** → main. It destroys the entire
   application state, checks empty state, an empty retained `rg-ecommerce-dev`,
   and surviving independent state/archive accounts. No foundation apply,
   role cleanup or LiveDocs handoff is required before each destroy.
5. As the operator, check the ACA managed resource group below is gone. Then
   explicitly run `apply` again with the same reviewed release and verify the
   URL/source identity again. Record both successful workflow URLs and the
   managed-group check as D/4 live evidence.

```powershell
az group exists --name rg-ecommerce-dev-aca-managed --output tsv
# Expected false after destruction. If true, inspect resources securely:
az resource list --resource-group rg-ecommerce-dev-aca-managed --output table
```

Azure owns this managed group and its infrastructure. Do not delete or import
its individual children. Investigate a residual group and reconcile the ACA
environment's deletion before recording clean teardown. The narrowly scoped
application identity cannot audit unrelated subscription resources. D/19 must
also inspect all retained/soft-deleted resources and actual billing.

## Allocation and cost limits

One external workload-profiles environment contains only its `Consumption`
profile. The app is single-revision, 0.25 vCPU / 0.5 GiB, min replicas 0, max 1,
HTTPS ingress to HTTP port 8080 and explicit startup/readiness/liveness probes.
No dedicated profile, Log Analytics workspace, private endpoint, NAT gateway,
APIM, Front Door, WAF or registry account is created. The VNet and delegated ACA
subnet are shared with the business apps later; public business ingress remains
BFF-only in D/9, while documentation has its own HTTPS endpoint.

**Minimum cost, not a guaranteed free deployment:**
[Microsoft documents additional managed networking charges](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks#managed-resources)
when supplying a custom VNet. These can continue while the app scales to zero;
destroy the environment when finished. The independent state and deliberately
persistent report archive remain billable for retained storage/transactions.
Consumption free allowances are shared at subscription level, not per app.

## Updating and rolling back the image

Review the publisher's immutable DockerHub digest and successful main source/run
metadata, then change `releases/livedocs.json` through an Infrastructure PR.
The release checker rejects mutable tags and mismatched publication provenance.
Do not trust a PR image as a production release. Infrastructure owns image
changes through Terraform; there is no `ignore_changes` or CLI revision updater.
A rollback restores a previously verified release file, then explicitly applies
its reviewed Terraform plan. Pushes/image publication cannot resurrect a
destroyed environment. This D/4 workflow intentionally rejects any extra
resources, deletes or replacements; D/15 extends that policy for the full system.
