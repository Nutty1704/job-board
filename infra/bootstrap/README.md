# Terraform bootstrap

This stack creates the AWS foundations that must exist before Buildkite can run
the application Terraform safely:

- a versioned S3 bucket for Terraform state and S3 lock files;
- a versioned private S3 bucket for immutable Lambda ZIPs;
- Buildkite's AWS OIDC provider;
- a plan role for every branch and an apply role restricted to `main`.

The first apply is deliberately local: the remote state bucket does not yet
exist. Immediately afterward, migrate this stack's state to
`job-board/bootstrap/terraform.tfstate` in the new bucket. The application
stack uses the separate `job-board/personal/terraform.tfstate` key.

## One-time bootstrap

Authenticate the AWS CLI as an administrator in the target account, then run:

```sh
export AWS_PROFILE=job-board-admin
export AWS_REGION=ap-southeast-2
aws sso login
aws sts get-caller-identity

just bootstrap-init-local
just bootstrap-fmt-check
just bootstrap-validate-local
just bootstrap-plan
just bootstrap-apply
```

`bootstrap-apply` creates only the two S3 buckets, Buildkite OIDC provider,
and the two Buildkite roles. Review its plan before confirming the apply.

Copy the bootstrap state to S3 immediately after the apply:

```sh
export TF_STATE_BUCKET="$(terraform -chdir=infra/bootstrap output -raw terraform_state_bucket_name)"
cp infra/bootstrap/backend.tf.example infra/bootstrap/backend.tf
just bootstrap-migrate-state
just bootstrap-init
```

Terraform asks for confirmation before copying the local state. Keep the local
state file as a recovery copy until `just bootstrap-plan` completes cleanly
using the remote backend. Both the local state file and copied backend file are
ignored by Git.

## Configure Buildkite

In the `job-board` pipeline settings, add these non-secret environment
variables from `just bootstrap-output`:

```text
TF_STATE_BUCKET=<terraform_state_bucket_name>
TF_VAR_ingestion_lambda_s3_bucket=<lambda_artifacts_bucket_name>
TERRAFORM_PLAN_ROLE_ARN=<terraform_plan_role_arn>
TERRAFORM_APPLY_ROLE_ARN=<terraform_apply_role_arn>
```

The pipeline configuration supplies `TF_VAR_ingestion_lambda_s3_key` from the
commit SHA for plans. It is safe for that object not to exist on feature
branches because a plan does not deploy the Lambda. A main-branch deployment
will upload that exact ZIP before applying Terraform.

The initial apply role has AWS `AdministratorAccess` because this new account
is dedicated to the project. Its trust policy is constrained to the named
Buildkite organization, pipeline, `main` branch, and `terraform-apply` step.
Replace the managed policy with a project-specific policy once the resource
set stabilizes.

The bootstrap avoids cross-region replication, S3 access logging, S3 event
notifications, and customer-managed KMS keys for this single-account personal
MVP. These decisions are documented as centralized Checkov exceptions in the
repository root `.checkov.yml`.
