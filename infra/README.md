# Infrastructure

The first Terraform milestone provisions the daily Adzuna ingestion flow:

```text
EventBridge Scheduler -> ingestion Lambda -> jobs-to-score SQS -> DLQ
```

It also creates the Lambda's least-privilege IAM roles, its Adzuna credential
container in Secrets Manager, CloudWatch logging, and two basic failure alarms.
The function intentionally remains outside a VPC for this phase: it has no
database dependency, and this avoids creating a NAT Gateway before the
database-connected workers exist.

## Before applying

1. Apply [`bootstrap/`](bootstrap/README.md) once to create the Terraform state
   and Lambda artifact buckets plus Buildkite OIDC roles.
2. Set `TF_STATE_BUCKET` to the bootstrap stack's
   `terraform_state_bucket_name` output, then run `just terraform-init`.
3. Build and upload an ingestion Lambda ZIP to the bootstrap stack's artifact
   bucket.
4. Copy `terraform.tfvars.example` to an untracked `terraform.tfvars` and set
   the artifact bucket/key.
5. Run `terraform plan`, then `terraform apply` from this directory.
6. Populate the created Adzuna secret directly in AWS. Terraform deliberately
   creates no `aws_secretsmanager_secret_version`, so credentials cannot enter
   source control or Terraform state.

VPC/NAT, RDS, OpenAI, matching, S3 resume storage, and the resume worker are
intentionally deferred to later milestones.
