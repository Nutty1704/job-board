resource "aws_secretsmanager_secret" "adzuna" {
  name                    = "${local.name_prefix}/adzuna"
  description             = "Adzuna API credentials for the scheduled ingestion Lambda."
  recovery_window_in_days = 7
}
