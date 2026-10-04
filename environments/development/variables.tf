variable "location" {
  description = "Azure region for disposable development resources. Eligibility is verified in D/5."
  type        = string
  default     = "northeurope"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]+$", var.location))
    error_message = "Use the Azure region identifier, for example northeurope."
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
