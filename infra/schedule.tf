resource "aws_scheduler_schedule" "ingestion" {
  name                         = "${local.name_prefix}-daily-ingestion"
  description                  = "Runs the Adzuna ingestion Lambda daily."
  schedule_expression          = var.ingestion_schedule_expression
  schedule_expression_timezone = "Australia/Sydney"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.ingestion.arn
    role_arn = aws_iam_role.ingestion_scheduler.arn

    dead_letter_config {
      arn = aws_sqs_queue.ingestion_invocation_dlq.arn
    }

    retry_policy {
      maximum_event_age_in_seconds = 86400
      maximum_retry_attempts       = 3
    }
  }
}

resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.ingestion.arn
}
