# ADR 0003: Application-owned LiveDocs deployment

Date: 2026-10-04
Status: Accepted for D/4; live Azure lifecycle verification pending.

## Context

LiveDocs publishes a static documentation container. The application needs a
sixth ACA host and one-button destruction while preserving its report archive.
A separate image-delivery Azure workflow would require overlapping ownership
and coordination with application Terraform during destroy/reapply.

## Decision

LiveDocs owns building, testing, scanning and publishing immutable images and
source metadata. Infrastructure owns all Azure resources and Terraform image
updates. Reusable modules create the shared VNet/Consumption environment and
small HTTPS host. A main-only manual plan/apply workflow uses the existing
application backend and `terraform-development` concurrency group. Pushes and
new images never deploy automatically or re-create a destroyed environment.

The archive is managed in Infrastructure's operator-only `foundations/livedocs`
root, using its own persistent container/key in the externally created state
account. The archive has private blob access, Entra authentication, version and
deletion retention, `prevent_destroy` and a management lock. The application
identity receives account Reader for retention checks only. Future report
producer/assembler data identities are LiveDocs LD/4, not runtime host access.

Application destroy owns the host, environment and network, and protects the
retained development group and both persistent storage boundaries. No separate
LiveDocs delivery identity, OIDC credential, app-scoped role assignment,
lease/gate blob or recurring privileged foundation cleanup is required.

## Consequences

A new image is deployed through a reviewed Infrastructure release-file change
and manual saved-plan apply. Rollback uses a previously verified digest/source.
The six apps share one environment rather than adding a documentation-only
managed environment. The custom VNet supports later business-network setup but
adds platform networking costs that continue at zero replicas; see
[Microsoft's managed-resource documentation](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks#managed-resources).
The external archive and state store incur retained storage/transaction costs.

Offline Terraform/provider and workflow tests do not establish live Azure
compatibility or successful cleanup. First apply → smoke → destroy → managed
resource audit → reapply evidence remains required in the runbook. Authentication
and additional hardening remain later iterations.
