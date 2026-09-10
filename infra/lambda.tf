resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/aws/lambda/${local.name_prefix}-ingestion"
  retention_in_days = 30
}

resource "aws_lambda_function" "ingestion" {
  #checkov:skip=CKV_AWS_117: This phase has no private dependency; VPC/NAT begins with the RDS workers.
  #checkov:skip=CKV_AWS_272: Code-signing will be added with the CI artifact-publishing pipeline.
  #checkov:skip=CKV_AWS_50: X-Ray is deferred until the multi-worker processing flow exists.
  function_name                  = "${local.name_prefix}-ingestion"
  description                    = "Fetches software-engineering jobs from configured Australian locations and queues them for scoring."
  role                           = aws_iam_role.ingestion_lambda.arn
  runtime                        = var.ingestion_lambda_runtime
  handler                        = var.ingestion_lambda_handler
  timeout                        = 120
  memory_size                    = 512
  reserved_concurrent_executions = 1

  s3_bucket         = var.ingestion_lambda_s3_bucket
  s3_key            = var.ingestion_lambda_s3_key
  s3_object_version = var.ingestion_lambda_s3_object_version

  environment {
    variables = {
      ADZUNA_COUNTRY          = var.adzuna_country
      ADZUNA_LOCATION         = var.adzuna_location
      ADZUNA_SEARCH_QUERY     = var.adzuna_search_query
      ADZUNA_RESULTS_PER_PAGE = var.adzuna_results_per_page
      ADZUNA_SECRET_ARN       = aws_secretsmanager_secret.adzuna.arn
      JOBS_TO_SCORE_QUEUE_URL = aws_sqs_queue.jobs_to_score.url
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.ingestion_invocation_dlq.arn
  }

  depends_on = [aws_cloudwatch_log_group.ingestion]
}
