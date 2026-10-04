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

# Resource modules are added in D/6-D/8 after D/4's release inventory and
# D/5's free-database compatibility gate. Do not own the retained group here.
