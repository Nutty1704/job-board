resource "aws_dynamodb_table" "job_matches" {
  #checkov:skip=CKV_AWS_119: AWS-owned encryption avoids a customer-managed KMS key's recurring cost for this personal project.
  name         = "${local.name_prefix}-job-matches"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "source"
  range_key    = "source_job_id"

  attribute {
    name = "source"
    type = "S"
  }

  attribute {
    name = "source_job_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_s3_bucket" "project_data" {
  bucket = local.name_prefix
}

resource "aws_s3_bucket_versioning" "project_data" {
  bucket = aws_s3_bucket.project_data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "project_data" {
  bucket = aws_s3_bucket.project_data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "project_data" {
  bucket                  = aws_s3_bucket.project_data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "project_data" {
  bucket = aws_s3_bucket.project_data.id

  rule {
    id     = "RetainPreviousVersions"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

resource "aws_cloudwatch_log_group" "matching" {
  name              = "/aws/lambda/${local.name_prefix}-matching"
  retention_in_days = 7
}

resource "aws_lambda_function" "matching" {
  #checkov:skip=CKV_AWS_117: The matching Lambda needs public HTTPS access to OpenAI and is intentionally outside a VPC.
  #checkov:skip=CKV_AWS_272: Code-signing is deferred until the CI artifact pipeline is expanded.
  #checkov:skip=CKV_AWS_50: X-Ray is deferred for this MVP worker.
  #checkov:skip=CKV_AWS_116: SQS source-message failures redrive to jobs-to-score-dlq; Lambda DLQs do not handle SQS event-source failures.
  function_name                  = "${local.name_prefix}-matching"
  description                    = "Filters and embeds normalized jobs before publishing high matches."
  role                           = aws_iam_role.matching_lambda.arn
  runtime                        = var.matching_lambda_runtime
  handler                        = var.matching_lambda_handler
  timeout                        = 60
  memory_size                    = 512
  reserved_concurrent_executions = 1
  s3_bucket                      = var.matching_lambda_s3_bucket
  s3_key                         = var.matching_lambda_s3_key
  s3_object_version              = var.matching_lambda_s3_object_version

  environment {
    variables = {
      JOBS_TO_SCORE_QUEUE_URL   = aws_sqs_queue.jobs_to_score.url
      HIGH_MATCH_JOBS_QUEUE_URL = aws_sqs_queue.high_match_jobs.url
      JOB_MATCHES_TABLE         = aws_dynamodb_table.job_matches.name
      MATCHING_PROFILE_BUCKET   = aws_s3_bucket.project_data.bucket
      MATCHING_PROFILE_KEY      = "matching/current.json"
      MATCHING_PROFILE_REGION   = var.aws_region
      OPENAI_PARAMETER_NAME     = aws_ssm_parameter.openai.name
      OPENAI_EMBEDDING_MODEL    = "text-embedding-3-small"
      MATCHING_BATCH_SIZE       = "10"
      MATCHING_LEASE_SECONDS    = "120"
      MATCHING_SCORE_THRESHOLD  = ""
    }
  }

  depends_on = [aws_cloudwatch_log_group.matching]
}

resource "aws_lambda_event_source_mapping" "matching_jobs_to_score" {
  event_source_arn                   = aws_sqs_queue.jobs_to_score.arn
  function_name                      = aws_lambda_function.matching.arn
  batch_size                         = 10
  function_response_types            = ["ReportBatchItemFailures"]
  maximum_batching_window_in_seconds = 5
}
