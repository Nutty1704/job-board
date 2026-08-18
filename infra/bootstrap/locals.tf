locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  }

  terraform_state_bucket_name  = "${local.name_prefix}-tf-state-${data.aws_caller_identity.current.account_id}"
  lambda_artifacts_bucket_name = "${local.name_prefix}-lambda-artifacts-${data.aws_caller_identity.current.account_id}"
  application_state_key        = "job-board/personal/terraform.tfstate"
}
