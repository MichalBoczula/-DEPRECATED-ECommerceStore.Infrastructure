# Disposable business file and secret services

Creates a Standard LRS Hot StorageV2 account, private `invoices`/`photos`
containers and a Standard RBAC Key Vault. The caller supplies names, tenant,
resource group, tags and the ACA subnet. Both services deny other networks;
Storage shared keys and blob public access are disabled. Container operations
use ARM with the pinned AzureRM provider.

No secrets or role assignments are created. D/9 owns runtime identities and
scoped data roles. The development root purges the disposable vault on destroy;
operators need purge permission. The persistent LiveDocs archive is separate.

See the [D/8 local runbook](../../docs/development-data-services.md). Module
outputs expose only endpoints, names and resource IDs. Use Terraform 1.16.5
and AzureRM 5.8.0 with the committed readonly lock file.
