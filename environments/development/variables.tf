variable "location" {
  description = "Azure region for disposable development resources. Eligibility is verified in D/6."
  type        = string
  default     = "northeurope"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]+$", var.location))
    error_message = "Use the Azure region identifier, for example northeurope."
  }
}

variable "enable_livedocs" {
  description = "Explicit D/4 deployment; false preserves the initial backend-only checks."
  type        = bool
  default     = false
}

variable "name_prefix" {
  description = "Short lowercase application prefix. This cannot change the retained group or backend."
  type        = string
  default     = "ecommerce"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,9}$", var.name_prefix))
    error_message = "name_prefix must contain 3-10 lowercase alphanumeric characters, starting with a letter."
  }
}

variable "tags" {
  description = "Additional non-secret metadata tags; mandatory ownership and cost tags are protected by the context module."
  type        = map(string)
  default     = {}
}

variable "enable_database_candidate" {
  description = "D/6 disposable experiment; not a selected production database."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_database_candidate || var.location == "northeurope"
    error_message = "The D/6 Mongo Free candidate remains in northeurope; use candidate_sql_location to move SQL independently."
  }
}
variable "candidate_sql_location" {
  description = "SQL-only region; check subscription availability before the first Free database creation. Keep unchanged while SQL resources exist."
  type        = string
  default     = "northeurope"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]+$", var.candidate_sql_location))
    error_message = "Use an Azure region identifier for SQL, for example westeurope."
  }
}
variable "candidate_suffix" {
  description = "Operator-chosen globally unique naming suffix; keep unchanged while these resources exist."
  type        = string
  default     = "unconfigured"
  validation {
    condition     = !var.enable_database_candidate || (var.candidate_suffix != "unconfigured" && can(regex("^[a-z0-9]{6,16}$", var.candidate_suffix)))
    error_message = "Configure a 6-16 lowercase alphanumeric candidate suffix before enabling D/6."
  }
}
variable "candidate_sql_password" {
  description = "D/6 SQL operator credential, provided as a secret; retained in protected state."
  type        = string
  default     = null
  sensitive   = true
  validation {
    condition     = !var.enable_database_candidate || try(length(var.candidate_sql_password) >= 16 && length(var.candidate_sql_password) <= 128, false)
    error_message = "Supply a strong 16-128 character SQL secret for the enabled candidate."
  }
}
variable "candidate_mongo_password" {
  description = "D/6 Mongo operator credential, provided as a secret; retained in protected state."
  type        = string
  default     = null
  sensitive   = true
  validation {
    condition     = !var.enable_database_candidate || try(length(var.candidate_mongo_password) >= 16 && length(var.candidate_mongo_password) <= 128, false)
    error_message = "Supply a strong 16-128 character Mongo secret for the enabled candidate."
  }
}
