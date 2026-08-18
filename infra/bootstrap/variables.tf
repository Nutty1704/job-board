variable "aws_region" {
  description = "AWS region for this personal environment."
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Short project name used in AWS resource names."
  type        = string
  default     = "job-board"
}

variable "environment" {
  description = "Environment name. This MVP provisions one personal environment."
  type        = string
  default     = "personal"
}

variable "buildkite_organization_slug" {
  description = "Buildkite organization slug permitted to assume Terraform roles."
  type        = string
  default     = "abhijit-upadhyay"
}

variable "buildkite_pipeline_slug" {
  description = "Buildkite pipeline slug permitted to assume Terraform roles."
  type        = string
  default     = "job-board"
}
