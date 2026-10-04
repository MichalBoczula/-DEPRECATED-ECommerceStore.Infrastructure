# Reusable Terraform modules

Current module: [deployment-context](deployment-context/README.md), a
provider-free naming and tagging contract shared by development and portfolio.
Resource modules will be added during the corresponding ACA, storage, database
and web deployment tasks. D/3 intentionally creates no application resources.

## Version contract

`modules/VERSION` versions all modules together. The initial version is `0.1.0`.
Successful main-branch Terraform CI triggers tag publication at that exact tested
commit. The initial `modules-v0.1.0` tag is available only after D/3 is merged and
main CI and publication succeed. The publisher has repository contents write
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
