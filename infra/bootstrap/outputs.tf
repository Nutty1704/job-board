output "aws_account_id" {
  description = "AWS account that owns this environment."
  value       = data.aws_caller_identity.current.account_id
}

output "terraform_state_bucket_name" {
  description = "Versioned S3 bucket used for Terraform state."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "lambda_artifacts_bucket_name" {
  description = "Versioned S3 bucket for immutable Lambda deployment packages."
  value       = aws_s3_bucket.lambda_artifacts.bucket
}

output "terraform_plan_role_arn" {
  description = "Buildkite OIDC role for feature-branch Terraform plans."
  value       = aws_iam_role.terraform_plan.arn
}

output "terraform_apply_role_arn" {
  description = "Buildkite OIDC role for approved main-branch applies."
  value       = aws_iam_role.terraform_apply.arn
}

output "ci_s3_publisher_role_arn" {
  description = "Buildkite OIDC role for publishing project artifacts to S3."
  value       = aws_iam_role.ci_s3_publisher.arn
}
