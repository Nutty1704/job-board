variable "aws_region" {
  description = "AWS region for the personal environment."
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

variable "ingestion_lambda_s3_bucket" {
  description = "S3 bucket containing the packaged ingestion Lambda ZIP."
  type        = string
}

variable "ingestion_lambda_s3_key" {
  description = "S3 object key for the packaged ingestion Lambda ZIP."
  type        = string
}

variable "ingestion_lambda_s3_object_version" {
  description = "Optional immutable S3 object version for the ingestion Lambda ZIP."
  type        = string
  default     = null
}

variable "ingestion_lambda_handler" {
  description = "Python handler exposed by the ingestion Lambda package."
  type        = string
  default     = "job_ingestion.lambda_handler"
}

variable "ingestion_lambda_runtime" {
  description = "Lambda runtime for the ingestion function."
  type        = string
  default     = "python3.12"
}

variable "adzuna_search_query" {
  description = "Initial Adzuna search query."
  type        = string
  default     = "software engineer"
}

variable "adzuna_location" {
  description = "Initial Adzuna search location."
  type        = string
  default     = "Sydney"
}

variable "adzuna_country" {
  description = "Adzuna country code."
  type        = string
  default     = "au"
}

variable "ingestion_schedule_expression" {
  description = "Daily EventBridge Scheduler expression, interpreted in Australia/Sydney time."
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "alarm_actions" {
  description = "Optional SNS topic ARNs to notify when phase-one alarms enter ALARM."
  type        = list(string)
  default     = []
}
