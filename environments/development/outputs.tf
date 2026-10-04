output "deployment_context" {
  description = "Non-secret naming and ownership contract consumed by future resource modules."
  value = {
    environment         = local.environment
    resource_group_name = local.retained_resource_group_name
    location            = module.context.location
    name_prefix         = module.context.name_prefix
    tags                = module.context.tags
  }
}
