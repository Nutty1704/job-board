resource "aws_iam_openid_connect_provider" "buildkite" {
  url             = "https://agent.buildkite.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["06b25927c42a721631c1efd9431e648fa62e1e39"]
}

data "aws_iam_policy_document" "buildkite_plan_assume_role" {
  statement {
    effect = "Allow"

    actions = ["sts:AssumeRoleWithWebIdentity", "sts:TagSession"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.buildkite.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "agent.buildkite.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "agent.buildkite.com:sub"
      values = [
        "organization:${var.buildkite_organization_slug}:pipeline:${var.buildkite_pipeline_slug}:ref:refs/heads/*:commit:*:step:terraform-plan",
      ]
    }
  }
}

resource "aws_iam_role" "terraform_plan" {
  name               = "${local.name_prefix}-terraform-plan"
  assume_role_policy = data.aws_iam_policy_document.buildkite_plan_assume_role.json
}

resource "aws_iam_role_policy_attachment" "terraform_plan_read_only" {
  role       = aws_iam_role.terraform_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "terraform_plan_state" {
  statement {
    sid       = "ListApplicationState"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.terraform_state.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.application_state_key}*"]
    }
  }

  statement {
    sid       = "ReadAndUpdateApplicationState"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.terraform_state.arn}/${local.application_state_key}"]
  }

  statement {
    sid       = "ManageApplicationStateLock"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.terraform_state.arn}/${local.application_state_key}.tflock"]
  }
}

resource "aws_iam_role_policy" "terraform_plan_state" {
  name   = "${local.name_prefix}-terraform-plan-state"
  role   = aws_iam_role.terraform_plan.id
  policy = data.aws_iam_policy_document.terraform_plan_state.json
}

data "aws_iam_policy_document" "buildkite_apply_assume_role" {
  statement {
    effect = "Allow"

    actions = ["sts:AssumeRoleWithWebIdentity", "sts:TagSession"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.buildkite.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "agent.buildkite.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "agent.buildkite.com:sub"
      values = [
        "organization:${var.buildkite_organization_slug}:pipeline:${var.buildkite_pipeline_slug}:ref:refs/heads/main:commit:*:step:terraform-apply",
      ]
    }
  }
}

resource "aws_iam_role" "terraform_apply" {
  name               = "${local.name_prefix}-terraform-apply"
  assume_role_policy = data.aws_iam_policy_document.buildkite_apply_assume_role.json
}

resource "aws_iam_role_policy_attachment" "terraform_apply_administrator" {
  role       = aws_iam_role.terraform_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
