resource "aws_dynamodb_table" "resume_generations" {
  #checkov:skip=CKV_AWS_119: AWS-owned encryption avoids a customer-managed KMS key's recurring cost for this personal project.
  name         = "${local.name_prefix}-resume-generations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "generation_id"

  attribute {
    name = "generation_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_cloudwatch_log_group" "resume" {
  name              = "/aws/lambda/${local.name_prefix}-resume"
  retention_in_days = 7
}

resource "aws_lambda_function" "resume" {
  #checkov:skip=CKV_AWS_117: The resume Lambda needs public HTTPS access to OpenAI and is intentionally outside a VPC.
  #checkov:skip=CKV_AWS_272: Code-signing is deferred for this MVP worker.
  #checkov:skip=CKV_AWS_50: X-Ray is deferred for this MVP worker.
  #checkov:skip=CKV_AWS_116: SQS source-message failures redrive to high-match-jobs-dlq.
  function_name                  = "${local.name_prefix}-resume"
  description                    = "Generates a fact-only DOCX resume for each qualified job."
  role                           = aws_iam_role.resume_lambda.arn
  runtime                        = var.resume_lambda_runtime
  handler                        = var.resume_lambda_handler
  timeout                        = 90
  memory_size                    = 512
  reserved_concurrent_executions = 1
  s3_bucket                      = var.resume_lambda_s3_bucket
  s3_key                         = var.resume_lambda_s3_key
  s3_object_version              = var.resume_lambda_s3_object_version

  environment {
    variables = {
      RESUME_GENERATIONS_TABLE = aws_dynamodb_table.resume_generations.name
      MATCHING_PROFILE_BUCKET  = aws_s3_bucket.project_data.bucket
      MATCHING_PROFILE_KEY     = "matching/current.json"
      RESUME_TEMPLATE_BUCKET   = aws_s3_bucket.project_data.bucket
      RESUME_TEMPLATE_KEY      = "resumes/templates/current.docx"
      OPENAI_PARAMETER_NAME    = aws_ssm_parameter.openai.name
      RESUME_LEASE_SECONDS     = "300"
    }
  }

  depends_on = [aws_cloudwatch_log_group.resume]
}

resource "aws_lambda_event_source_mapping" "resume_high_match_jobs" {
  event_source_arn        = aws_sqs_queue.high_match_jobs.arn
  function_name           = aws_lambda_function.resume.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
}
