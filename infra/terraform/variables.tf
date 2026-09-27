variable "stage" {
  type    = string
  default = "dev"
  validation {
    condition     = contains(["dev", "qa", "prd"], var.stage)
    error_message = "stage must be dev, qa, or prd"
  }
}

variable "owner_name" {
  type    = string
  default = "andre"
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "expected_account_id" {
  type        = string
  description = "Account Terraform is allowed to modify; supplied by AWS_ACCOUNT_ID through with-env.ps1"
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID"
  }
}

variable "production_queue_name" {
  type        = string
  description = "Existing production source queue; Terraform reads but never owns it"
  default     = "openaq-andre"
}

variable "enable_ingestion" {
  type        = bool
  description = "Enable the production queue consumer only after deployment smoke tests"
  default     = false
}

variable "enable_schedule" {
  type        = bool
  description = "Enable scheduled production transformations only after ingestion is ready"
  default     = false
}
