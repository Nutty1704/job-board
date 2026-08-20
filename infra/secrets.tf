resource "aws_secretsmanager_secret" "adzuna" {
  name                    = "${local.name_prefix}/adzuna"
  description             = "Adzuna API credentials for the scheduled ingestion Lambda."
  recovery_window_in_days = 7
}

resource "aws_ssm_parameter" "openai" {
  name        = "/${local.name_prefix}/openai"
  description = "OpenAI API key JSON for the matching Lambda; populate api_key outside Terraform."
  type        = "SecureString"
  tier        = "Standard"
  value       = "replace-me"

  lifecycle {
    ignore_changes = [value]
  }
}
