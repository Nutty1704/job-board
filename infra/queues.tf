resource "aws_sqs_queue" "jobs_to_score_dlq" {
  name                      = "${local.name_prefix}-jobs-to-score-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "ingestion_invocation_dlq" {
  name                      = "${local.name_prefix}-ingestion-invocation-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "jobs_to_score" {
  name                       = "${local.name_prefix}-jobs-to-score"
  message_retention_seconds  = 345600 # 4 days
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_to_score_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "high_match_jobs_dlq" {
  name                      = "${local.name_prefix}-high-match-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "high_match_jobs" {
  name                       = "${local.name_prefix}-high-match-jobs"
  message_retention_seconds  = 345600 # 4 days
  visibility_timeout_seconds = 600
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.high_match_jobs_dlq.arn
    maxReceiveCount     = 3
  })
}
