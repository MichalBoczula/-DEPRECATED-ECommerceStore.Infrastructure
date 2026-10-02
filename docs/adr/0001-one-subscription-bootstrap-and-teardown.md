# ADR 0001: Persistent access boundary in one Azure subscription

Status: Accepted by the user on 2026-10-02.

## Context

The portfolio must use one Azure subscription, an independent Terraform state
repository, passwordless CI deployment and disposable application resources.
Subscription-wide Contributor would include backend resource-management access.
RG-scoped access disappears if its resource group is deleted, so it cannot
independently recreate the next environment using the same narrow permissions.

## Decision

`ECommerceStore.TerraformState` owns the state storage, persistent OIDC deployment
identity, an empty `rg-ecommerce-dev` and RG-scoped access assignments. The app
state owns its children. The custom management role excludes deletion of the
group and access-management/lock writes. Backend account management is Reader;
state data permissions are limited to `development-state`. Bootstrap's own
state uses a separate container/key. Application role-assignment delegation is
disabled until D/7 needs specific data roles.

## Consequences

Destroy now means all disposable application resources and data, with state
empty and the retained group empty. The original D/1 group-absence check is
replaced by group-presence plus zero children. Persistent identity/access and
backend survive. A rebuild does not require subscription-wide deployment grants
or a privileged resource-group recreation step.

The empty group is a deliberate lifecycle exception, not a running service.
State storage and retained blob versions still have a small persistent footprint.
Portfolio will receive a different group/container/identity during P/2.
Subscription-level operations such as provider registration and budget setup
must be performed by the bootstrap operator. No paid networking or gateway is
introduced. Full removal and residual-cost verification remain in D/18.
