# Reusable Terraform modules

Modules: [deployment-context](deployment-context/README.md),
[consumption-environment](consumption-environment/README.md) and
[livedocs](livedocs/README.md). Development tests these together using local
sources. The ACA environment is shared by LiveDocs now and the five business
apps in D/9. Persistent archive storage is a separate operator root, not a
module in application state.

## Version contract

`modules/VERSION` versions all modules together. D/7 proposes version `0.3.0` for the subnet endpoint change.
Successful main-branch Terraform CI triggers tag publication at that exact tested
commit. `modules-v0.1.0` and `modules-v0.2.0` are published. The new tag becomes available after D/7 is
merged and its main CI and publication succeed. The publisher has repository contents write
permission and no Azure access. It never overwrites a tag.

Change module files and bump `modules/VERSION` in the same PR. If a version
already exists, publication succeeds only when its module content matches the
tested commit. Changed content without a bump fails publication. Review tag
and workflow results before upgrading a consumer. This is a versioned Git
module distribution, not a Terraform Registry release.

Development uses local modules so a PR tests the root and module changes
together. Portfolio uses an immutable release reference, for example after
the initial release:

```hcl
module "context" {
  source       = "git::https://github.com/MichalBoczula/ECommerceStore.Infrastructure.git//modules/deployment-context?ref=modules-v0.1.0"
  project      = "ECommerceStore"
  environment  = "portfolio"
  name_prefix  = "ecommerce"
  location     = "northeurope"
  cost_profile = "interview"
}
```

Do not reference `main` from portfolio. A module upgrade is an explicit change
to its `ref`, followed by a reviewed plan. Keep the previous configuration and
state until teardown or upgrade succeeds; a Git rollback alone does not undo
Azure changes.

D/5's release manifest retains its verified `modules-v0.2.0` publication
provenance. Development tests D/7 against local 0.3.0 modules. Update consumer
release provenance only after the new immutable tag has actually been published.
