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
3. Copy `terraform.tfvars.example` to an untracked `terraform.tfvars` and set
   the artifact bucket/key for local development.
4. On `main`, Buildkite annotates whether `apps/ingestion/` changed. If it
   did, approve the **Publish ingestion Lambda** block to package and upload a
   commit-keyed ZIP to the versioned artifact bucket.
5. Review the plan, then approve the Buildkite **Apply** block. When an
   ingestion artifact was published, the apply step uses its exact S3 object
   version; otherwise it applies only the infrastructure changes.
6. Populate the created Adzuna secret directly in AWS. Terraform deliberately
   creates no `aws_secretsmanager_secret_version`, so credentials cannot enter
   source control or Terraform state.

VPC/NAT, RDS, OpenAI, matching, S3 resume storage, and the resume worker are
intentionally deferred to later milestones.

## Adzuna configuration

After the first apply, place this JSON value in the `adzuna_secret_arn` output
using the AWS console or CLI:

```json
{ "app_id": "your-adzuna-app-id", "app_key": "your-adzuna-app-key" }
```

Never put either credential in Terraform variables, source control, or CI
logs. The Lambda receives the secret ARN and these non-secret environment
variables from Terraform: `ADZUNA_COUNTRY`, `ADZUNA_LOCATION`,
`ADZUNA_SEARCH_QUERY`, `ADZUNA_RESULTS_PER_PAGE`, and
`JOBS_TO_SCORE_QUEUE_URL`. `adzuna_results_per_page` defaults to 50 and must
be between 1 and 50; page one is always fetched in this MVP.

For a local deployment, upload and capture the object version before applying:

```sh
ARTIFACT_BUCKET="$(terraform -chdir=infra/bootstrap output -raw lambda_artifacts_bucket_name)"
aws s3api put-object --bucket "$ARTIFACT_BUCKET" --key "lambdas/ingestion/$(git rev-parse HEAD).zip" --body dist/ingestion.zip
```

Use the `VersionId` returned by `put-object` as
`ingestion_lambda_s3_object_version` and the same key as
`ingestion_lambda_s3_key` in the untracked `infra/terraform.tfvars`. This
keeps Terraform deployments pinned to the exact ZIP that was tested.

Buildkite uses a dedicated `ci_s3_publisher` role for the manually approved
artifact upload. It can only put objects in the Lambda artifact bucket; the
administrator-scoped Terraform apply role remains limited to the manually
approved apply step.
