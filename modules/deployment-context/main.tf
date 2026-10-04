locals {
  environment_suffix = var.environment == "development" ? "dev" : "portfolio"
  name_prefix        = "${var.name_prefix}-${local.environment_suffix}"
  tags = merge(var.tags, {
    project     = var.project
    environment = var.environment
    managedBy   = "Terraform"
    lifecycle   = "disposable"
    costProfile = var.cost_profile
  })
}
