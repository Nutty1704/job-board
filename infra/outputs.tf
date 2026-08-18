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
