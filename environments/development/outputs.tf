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

output "livedocs" {
  value = var.enable_livedocs ? {
    app_id                      = module.livedocs[0].id
    portal_url                  = module.livedocs[0].portal_url
    environment_id              = module.consumption[0].id
    managed_resource_group_name = module.consumption[0].managed_resource_group_name
    image                       = local.livedocs_release.image
    commit_sha                  = local.livedocs_release.commitSha
  } : null
}
