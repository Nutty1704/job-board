resource "aws_cloudwatch_metric_alarm" "ingestion_errors" {
  alarm_name          = "${local.name_prefix}-ingestion-errors"
  alarm_description   = "The scheduled ingestion Lambda reported an error."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 86400
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  dimensions = {
    FunctionName = aws_lambda_function.ingestion.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "jobs_to_score_dlq_messages" {
  alarm_name          = "${local.name_prefix}-jobs-to-score-dlq-messages"
  alarm_description   = "Messages require inspection after repeated ingestion delivery failures."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  dimensions = {
    QueueName = aws_sqs_queue.jobs_to_score_dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "matching_errors" {
  alarm_name          = "${local.name_prefix}-matching-errors"
  alarm_description   = "The matching Lambda reported an error."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  dimensions          = { FunctionName = aws_lambda_function.matching.function_name }
}

resource "aws_cloudwatch_metric_alarm" "high_match_jobs_dlq_messages" {
  alarm_name          = "${local.name_prefix}-high-match-jobs-dlq-messages"
  alarm_description   = "High-match messages require inspection after repeated downstream delivery failures."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  dimensions          = { QueueName = aws_sqs_queue.high_match_jobs_dlq.name }
}

resource "aws_cloudwatch_metric_alarm" "resume_errors" {
  alarm_name          = "${local.name_prefix}-resume-errors"
  alarm_description   = "The resume Lambda reported an error."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  dimensions          = { FunctionName = aws_lambda_function.resume.function_name }
}
