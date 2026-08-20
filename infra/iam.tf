data "aws_iam_policy_document" "ingestion_lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingestion_lambda" {
  name               = "${local.name_prefix}-ingestion-lambda"
  assume_role_policy = data.aws_iam_policy_document.ingestion_lambda_assume_role.json
}

data "aws_iam_policy_document" "ingestion_lambda" {
  statement {
    sid       = "WriteLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingestion.arn}:*"]
  }

  statement {
    sid       = "ReadAdzunaCredentials"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.adzuna.arn]
  }

  statement {
    sid       = "EnqueueJobsForScoring"
    effect    = "Allow"
    actions   = ["sqs:SendMessage", "sqs:SendMessageBatch"]
    resources = [aws_sqs_queue.jobs_to_score.arn]
  }

  statement {
    sid       = "SendInvocationFailuresToDlq"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion_invocation_dlq.arn]
  }
}

resource "aws_iam_role_policy" "ingestion_lambda" {
  name   = "${local.name_prefix}-ingestion-lambda"
  role   = aws_iam_role.ingestion_lambda.id
  policy = data.aws_iam_policy_document.ingestion_lambda.json
}

data "aws_iam_policy_document" "matching_lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "matching_lambda" {
  name               = "${local.name_prefix}-matching-lambda"
  assume_role_policy = data.aws_iam_policy_document.matching_lambda_assume_role.json
}

data "aws_iam_policy_document" "matching_lambda" {
  statement {
    sid       = "WriteLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.matching.arn}:*"]
  }
  statement {
    sid       = "ReadOpenAiParameter"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.openai.arn]
  }
  statement {
    sid       = "ReadMatchingProfile"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.matching_profiles.arn}/current.json"]
  }
  statement {
    sid       = "ReadAndWriteJobMatches"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.job_matches.arn]
  }
  statement {
    sid       = "PublishHighMatches"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.high_match_jobs.arn]
  }
  statement {
    sid       = "ConsumeJobsToScore"
    effect    = "Allow"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
    resources = [aws_sqs_queue.jobs_to_score.arn]
  }
}

resource "aws_iam_role_policy" "matching_lambda" {
  name   = "${local.name_prefix}-matching-lambda"
  role   = aws_iam_role.matching_lambda.id
  policy = data.aws_iam_policy_document.matching_lambda.json
}

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingestion_scheduler" {
  name               = "${local.name_prefix}-ingestion-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
}

data "aws_iam_policy_document" "ingestion_scheduler" {
  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.ingestion.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion_invocation_dlq.arn]
  }
}

resource "aws_iam_role_policy" "ingestion_scheduler" {
  name   = "${local.name_prefix}-ingestion-scheduler"
  role   = aws_iam_role.ingestion_scheduler.id
  policy = data.aws_iam_policy_document.ingestion_scheduler.json
}
