locals {
  environment                  = "development"
  retained_resource_group_name = "rg-ecommerce-dev"
}

module "context" {
  source = "../../modules/deployment-context"

  project      = "ECommerceStore"
  environment  = local.environment
  name_prefix  = var.name_prefix
  location     = var.location
  cost_profile = "minimal"
  tags         = var.tags
}

locals {
  livedocs_release = jsondecode(file("${path.module}/../../releases/livedocs.json"))
}

module "consumption" {
  count               = var.enable_livedocs ? 1 : 0
  source              = "../../modules/consumption-environment"
  resource_group_name = local.retained_resource_group_name
  name_prefix         = module.context.name_prefix
  location            = var.location
  tags                = module.context.tags
}
module "livedocs" {
  count               = var.enable_livedocs ? 1 : 0
  source              = "../../modules/livedocs"
  resource_group_name = local.retained_resource_group_name
  environment_id      = module.consumption[0].id
  name                = "ca-${module.context.name_prefix}-livedocs"
  image               = local.livedocs_release.image
  tags                = module.context.tags
}
# Five business services join this environment in D/9 with Azure driver compatibility verification.
