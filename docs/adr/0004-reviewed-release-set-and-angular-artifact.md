# ADR 0004: reviewed immutable release set

Status: Accepted for the D/5 development inventory.

The service repositories already publish tested images independently. Terraform
must be able to recreate a reviewed environment without rebuilding several
repository heads or changing the selected application bytes during apply.

Record the five business image digests, full source commits and successful
publication runs/jobs in `releases/development.json`. Include the retained
LiveDocs pin, published Infrastructure module tag/commit, consumer contract
checksums and the frontend build/artifact identity. Commit registry metadata as
checksum-verifiable review evidence. PR CI validates the local inventory;
explicit public verification rechecks origin CI, registry bytes and contracts.
Later deployment/promotion workflows consume this manifest.

The current frontend publishes an Nginx image rather than a standalone SWA
archive. Record its final Angular COPY layer as the separate static artifact,
with per-file checksums and a verified extractor. This preserves already built
bytes without a second build. D/11 will publish a cloud-configured static
artifact and update the affected BFF/frontend pins together; the current
`/backend` proxy assumption and localhost-only CORS remain recorded blockers.

This adds no Azure resource, paid image registry, gateway or authentication
service. Public digest availability and CI evidence are checked, but signatures
and long-term artifact retention require later decisions. Local-container
compatibility evidence does not establish cloud database/Stripe/storage behavior.

Commit-named Docker tags may be removed while a selected digest remains
available. Preserve successful push-log provenance and verify the actual digest;
do not make recreation depend on resolving those mutable tag names.
