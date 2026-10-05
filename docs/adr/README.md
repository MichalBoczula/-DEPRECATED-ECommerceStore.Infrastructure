# Architecture decision records

| Decision | Status |
| --- | --- |
| [0001: Persistent access boundary in one Azure subscription](0001-one-subscription-bootstrap-and-teardown.md) | Accepted |
| [0002: Terraform roots, versioned modules and offline review CI](0002-terraform-modules-and-ci.md) | Implemented in D/3 |

Future gateway, private networking, authentication and warehouse decisions
belong to their iterations. The development MVP currently prioritizes minimal
cost, with no paid gateway or private endpoints.

- [0003: Application-owned LiveDocs deployment](0003-livedocs-application-owned-deployment.md)
- [0004: LiveDocs archive CI identities](0004-livedocs-archive-ci-identities.md)
