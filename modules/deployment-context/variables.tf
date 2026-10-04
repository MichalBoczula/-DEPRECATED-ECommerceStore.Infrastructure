variable "project" {
  description = "Non-secret project label used in mandatory ownership tags."
  type        = string
  validation {
    condition     = length(trimspace(var.project)) > 0 && length(var.project) <= 64
    error_message = "project must be a non-empty label of at most 64 characters."
  }
}

variable "environment" {
  description = "Deployment boundary; the module is shared, resources and state are not."
  type        = string
  validation {
    condition     = contains(["development", "portfolio"], var.environment)
    error_message = "environment must be development or portfolio."
  }
}

variable "name_prefix" {
  description = "Short lowercase application prefix; service modules append resource-specific names."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,9}$", var.name_prefix))
    error_message = "name_prefix must contain 3-10 lowercase alphanumeric characters, starting with a letter."
  }
}

variable "location" {
  description = "Azure region identifier. The consumer verifies availability of its chosen services."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]+$", var.location))
    error_message = "Use an Azure region identifier, for example northeurope."
  }
}

variable "cost_profile" {
  description = "Cost intent; this tag does not enforce Azure spend or select service SKUs."
  type        = string
  default     = "minimal"
  validation {
    condition     = contains(["minimal", "interview"], var.cost_profile) && (var.cost_profile != "interview" || var.environment == "portfolio")
    error_message = "cost_profile must be minimal, or interview for the portfolio environment."
  }
}

variable "tags" {
  description = "Additional non-secret metadata. Ownership and cost tags cannot be overridden, including by different casing."
  type        = map(string)
  default     = {}
  validation {
    condition = length(var.tags) <= 45 && alltrue([
      for key, value in var.tags :
      !contains(["project", "environment", "managedby", "lifecycle", "costprofile"], lower(key)) &&
      length(trimspace(key)) > 0 && length(key) <= 128 && length(value) <= 256
    ])
    error_message = "Use at most 45 additional valid tags; project/environment/managedBy/lifecycle/costProfile are reserved, case-insensitively."
  }
}
