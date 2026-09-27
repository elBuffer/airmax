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

variable "openaq_topic_arn" {
  type        = string
  description = "Public OpenAQ SNS topic ARN; required only for prd"
  default     = ""
  validation {
    condition     = var.stage != "prd" || startswith(var.openaq_topic_arn, "arn:aws:sns:")
    error_message = "openaq_topic_arn must be supplied for prd"
  }
}
