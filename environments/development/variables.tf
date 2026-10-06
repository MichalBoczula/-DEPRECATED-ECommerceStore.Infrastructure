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

variable "enable_shared_environment" {
  description = "D/7 shared ACA network without requiring the LiveDocs host; preserves existing module addresses."
  type        = bool
  default     = false
}

variable "enable_database_access" {
  description = "Explicit D/7 public TLS access restricted to discovered ACA outbound IPv4 addresses."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_database_access || (var.enable_database_candidate && (var.enable_shared_environment || var.enable_livedocs) && length(var.database_aca_ipv4) > 0)
    error_message = "Database access requires the candidate, shared ACA environment and a nonempty discovered outbound IPv4 set."
  }
}

variable "enable_data_services" {
  description = "D/8 disposable business Blob Storage and Key Vault. Independent of persistent LiveDocs archive."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_data_services || (var.enable_shared_environment || var.enable_livedocs)
    error_message = "Data services require the shared ACA subnet and its Storage/Key Vault service endpoints."
  }
}

variable "database_aca_ipv4" {
  description = "Observed ACA outbound addresses only; refresh after recreation or egress changes. No operator IP or CIDR ranges."
  type        = set(string)
  default     = []
  validation {
    condition     = length(var.database_aca_ipv4) <= 64 && alltrue([for ip in var.database_aca_ipv4 : try(cidrhost("${ip}/32", 0) == ip && !strcontains(ip, ":") && ip != "0.0.0.0", false)])
    error_message = "Use at most 64 individual canonical IPv4 addresses; no CIDR, IPv6 or allow-Azure-services address."
  }
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
