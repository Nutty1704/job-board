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
  default     = "lambdas/ingestion/latest.zip"
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

variable "matching_lambda_s3_bucket" {
  description = "S3 bucket containing the packaged matching Lambda ZIP."
  type        = string
}

variable "matching_lambda_s3_key" {
  description = "S3 object key for the packaged matching Lambda ZIP."
  type        = string
  default     = "lambdas/matching/latest.zip"
}

variable "matching_lambda_s3_object_version" {
  description = "Optional immutable S3 object version for the matching Lambda ZIP."
  type        = string
  default     = null
}

variable "matching_lambda_handler" {
  description = "Python handler exposed by the matching Lambda package."
  type        = string
  default     = "job_matching.lambda_handler"
}

variable "matching_lambda_runtime" {
  description = "Lambda runtime for the matching function."
  type        = string
  default     = "python3.12"
}

variable "resume_lambda_s3_bucket" {
  description = "S3 bucket containing the packaged resume Lambda ZIP."
  type        = string
}

variable "resume_lambda_s3_key" {
  description = "S3 object key for the packaged resume Lambda ZIP."
  type        = string
  default     = "lambdas/resume/latest.zip"
}

variable "resume_lambda_s3_object_version" {
  description = "Optional immutable S3 object version for the resume Lambda ZIP."
  type        = string
  default     = null
}

variable "resume_lambda_handler" {
  description = "Python handler exposed by the resume Lambda package."
  type        = string
  default     = "job_resume.lambda_handler"
}

variable "resume_lambda_runtime" {
  description = "Lambda runtime for the resume function."
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

variable "adzuna_results_per_page" {
  description = "Number of Adzuna results fetched from page one per invocation."
  type        = number
  default     = 50

  validation {
    condition     = var.adzuna_results_per_page >= 1 && var.adzuna_results_per_page <= 50
    error_message = "adzuna_results_per_page must be between 1 and 50."
  }
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

variable "dashboard_lambda_s3_bucket" {
  type        = string
  description = "S3 bucket containing the dashboard API Lambda ZIP."
}
variable "dashboard_lambda_s3_key" {
  type        = string
  default     = "lambdas/dashboard/latest.zip"
  description = "S3 key for the dashboard API Lambda ZIP."
}
variable "dashboard_lambda_s3_object_version" {
  type        = string
  default     = null
  description = "Optional immutable S3 object version for the dashboard API Lambda ZIP."
}
