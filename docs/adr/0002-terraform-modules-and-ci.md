# ADR 0002: Terraform roots, versioned modules and offline review CI

Status: Implemented in D/3, 2026-10-04.

## Context

Development and a temporary portfolio deployment need reusable infrastructure
without sharing state or granting untrusted PR code Azure access. Previous
Windows setup exposed Terraform-version and provider-checksum mismatches.
SQL Free requires properties missing from the selected AzureRM provider.

## Decision

Keep development's root in `environments/development` and reusable modules in
`modules`. Keep portfolio's root in its separate repository. Begin with a pure
deployment-context module; add resource modules as later tasks establish their
contracts. Keep the state store and retained group outside application ownership
as specified by ADR 0001.

Pin Terraform `1.16.5`, AzureRM `5.8.0` and AzAPI `2.13.0`; commit Windows and
Linux provider checksums and enforce readonly initialization. Disable automatic
provider registration. Audit provider schema support in CI. Reserve AzAPI for
SQL Free properties and the reviewed DocumentDB Free creation contract. D/6
provisions provisional resources and checks offer settings; D/9 must establish
application compatibility before accepting them for business rollout.

Run formatting, validation, mock plan tests and lifecycle contract tests on PRs
without Azure credentials. Summaries expose resource types, actions, counts and
output names, not plan values. Label them offline previews. Keep authenticated
backend/teardown workflows main-only. Real reviewed deployment plans are a
later workflow task and must share the lifecycle concurrency/state contract.

Version module contents together in `modules/VERSION`. After successful main
CI, a dedicated workflow publishes `modules-v<version>` at the tested commit.
It has no Azure permission and never moves existing tags. Development tests
local modules; portfolio pins released tags. Changed module contents require
a version bump.

## Consequences

PR checks cost no Azure resource runtime and support Windows contributors.
Mock plans cannot establish real Azure diffs, quota, offer eligibility or
runtime compatibility. Reusable modules have explicit upgrade references;
version publication waits for merged main CI. D/3 adds metadata outputs only,
so no new application infrastructure is billed by this change.
