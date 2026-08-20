output "ingestion_lambda_name" {
  description = "Name of the scheduled Adzuna ingestion Lambda."
  value       = aws_lambda_function.ingestion.function_name
}

output "jobs_to_score_queue_url" {
  description = "Queue URL for normalized jobs awaiting matching."
  value       = aws_sqs_queue.jobs_to_score.url
}

output "adzuna_secret_arn" {
  description = "Secret ARN whose value must be populated outside Terraform."
  value       = aws_secretsmanager_secret.adzuna.arn
}

output "ingestion_schedule_arn" {
  description = "ARN of the daily ingestion schedule."
  value       = aws_scheduler_schedule.ingestion.arn
}

output "matching_lambda_name" {
  description = "Name of the SQS matching Lambda."
  value       = aws_lambda_function.matching.function_name
}

output "matching_profile_bucket_name" {
  description = "Private versioned bucket containing profiles/current.json."
  value       = aws_s3_bucket.matching_profiles.bucket
}

output "high_match_jobs_queue_url" {
  description = "Queue for qualified jobs; consumers must tolerate duplicate deliveries."
  value       = aws_sqs_queue.high_match_jobs.url
}

output "openai_parameter_name" {
  description = "Standard SecureString whose value must be populated as {\"api_key\":\"…\"} outside Terraform."
  value       = aws_ssm_parameter.openai.name
}
