# Architecture decision records

| Decision | Status |
| --- | --- |
| [0001: Persistent access boundary in one Azure subscription](0001-one-subscription-bootstrap-and-teardown.md) | Accepted |
| [0002: Terraform roots, versioned modules and offline review CI](0002-terraform-modules-and-ci.md) | Implemented in D/3 |
| [0003: Application-owned LiveDocs deployment](0003-livedocs-application-owned-deployment.md) | Accepted for D/4 |
| [0004: Reviewed release set and Angular artifact](0004-reviewed-release-set-and-angular-artifact.md) | Accepted for D/5 |
| [0005: LiveDocs archive CI identities](0005-livedocs-archive-ci-identities.md) | Accepted for LD/5 |
| [0006: Local ACA database access](0006-local-aca-database-access.md) | D/7 implementation; live acceptance pending |

Future gateway, private networking, authentication and warehouse decisions
belong to their iterations. The development MVP currently prioritizes minimal
cost, with no paid gateway or private endpoints.
