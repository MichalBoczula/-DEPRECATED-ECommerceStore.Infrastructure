# ADR 0007: Disposable business Blob Storage and Key Vault

Status: D/8 implementation; live acceptance pending. Date: 2026-10-06.

Use one Standard LRS Hot StorageV2 business account with private invoices/photos
containers and one Standard RBAC Key Vault in the application state. Reuse
D/6's SQL server/database and single Free Mongo cluster. Record three service
Mongo database names; actual collections and indexes belong to D/9/D/10.

The existing ACA subnet has Storage and Key Vault service endpoints. Both
services allow only this subnet, deny other networks and disable trusted-service
bypass. Storage shared keys and public blobs are disabled. D/9 grants scoped
runtime identity permissions. This introduces no private endpoint, NAT gateway
or workstation firewall rule.

Keep runtime secret values outside Terraform using a hidden local prompt and
an ARM vaults/secrets write. Terraform creates the vault but no secret objects.
Administrator database passwords still reside in sensitive Terraform state.
This boundary does not remove the need to protect state or local request files.

All business data is synthetic and disposable. No Blob retention/versioning is
configured. Key Vault soft delete is unavoidable: purge protection stays off,
the root purges on destroy and disables automatic recovery. A local operator
must have deleted-vault purge permission; D/19 verifies residuals independently.

The persistent LiveDocs archive retains its separate root, data and CI identities.
D/8 does not bind the current file adapter to Blob or deploy business apps.
Local saved-plan lifecycle checks extend D/7, with live ARM readback after apply.
