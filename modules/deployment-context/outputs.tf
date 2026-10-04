output "name_prefix" {
  description = "Deterministic prefix separated by environment; globally unique resources need an additional suffix in their owning module."
  value       = local.name_prefix
}

output "location" {
  description = "Azure region shared by modules in this deployment."
  value       = var.location
}

output "tags" {
  description = "Additional tags plus mandatory ownership, lifecycle and cost intent."
  value       = local.tags
}
