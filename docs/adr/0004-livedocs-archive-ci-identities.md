# ADR-0004: CI identities for the persistent LiveDocs archive

- Status: Accepted for LD/5
- Date: 2026-10-05

## Context

Products publishes durable documentation bundles. LiveDocs verifies those bundles
and builds static images. Neither task needs application deployment privileges
or access to mobile-phone photos.

## Decision

Keep the existing persistent archive root and private `livedocs` container.
Terraform creates separate user-assigned managed identities for Products' writer
and LiveDocs' reader. Scope Blob Data Contributor/Reader to that container only.
Trust Products master pushes and two protected LiveDocs environments through
GitHub OIDC. Build/import access requires explicit branch restrictions; PR archive
access requires reviewer approval. Configure environments before applying
federation. Never create unrestricted pull_request federation.
Future services require explicit producer identities and federation, not reuse of
Products credentials. Do not attach either CI identity to the ACA host.

LiveDocs stores source identity, checksum and archive location in reviewed Git
manifests. CI authenticates and fetches inputs outside Docker. Products uploads
content-addressed bundles and candidate receipts; LiveDocs verifies successful
producer runs and opens its own PR using a repository-scoped GitHub App.

## Consequences

No account keys, SAS tokens or runtime archive credentials are required. Storage
and CI identities survive application teardown. The contributor role permits
deletes; overwrite refusal and checksums are application protections, not a WORM
policy. Preserve versioning, soft delete and every referenced package. Azure setup
and GitHub App installation are operator steps; offline CI does not apply them.

The persistent account currently contains the archive container. A photos
container can coexist in the same account with separate access roles; LD/5
does not create photo storage or migrate any existing account.

## Alternatives considered

- Reuse the application deployment identity: grants unrelated management access.
- Share photo storage credentials: broadens the archive trust boundary.
- Runtime archive mount: makes availability depend on storage and replica writes.
