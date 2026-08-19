#!/usr/bin/env bash
set -euo pipefail

annotation_context="ingestion-deployment"

if git rev-parse --verify "${BUILDKITE_COMMIT}^" >/dev/null 2>&1 \
  && git diff --quiet "${BUILDKITE_COMMIT}^" "${BUILDKITE_COMMIT}" -- apps/ingestion; then
  buildkite-agent annotate \
    "### Ingestion Lambda\n\nNo files under \`apps/ingestion/\` changed. This build will not publish a Lambda artifact." \
    --style info \
    --context "${annotation_context}"

  cat <<'YAML' | buildkite-agent pipeline upload
steps:
  - block: ":terraform: Apply"
    key: terraform-apply-approval
    depends_on: prepare-deployment

  - label: ":terraform: Apply"
    key: terraform-apply
    depends_on: terraform-apply-approval
    command: |
      : "$${TF_STATE_BUCKET:?TF_STATE_BUCKET must be set in Buildkite.}"
      just terraform-init
      terraform -chdir=infra apply -auto-approve
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: $TERRAFORM_APPLY_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    timeout_in_minutes: 15
YAML
  exit 0
fi

buildkite-agent annotate \
  "### Ingestion Lambda\n\nFiles under \`apps/ingestion/\` changed. Approve the publish step before Terraform can be applied." \
  --style warning \
  --context "${annotation_context}"

cat <<'YAML' | buildkite-agent pipeline upload
steps:
  - block: ":package: Publish ingestion Lambda"
    key: publish-ingestion-approval
    depends_on: prepare-deployment

  - label: ":package: Publish ingestion Lambda"
    key: publish-ingestion
    depends_on: publish-ingestion-approval
    command: |
      : "$${TF_VAR_ingestion_lambda_s3_bucket:?TF_VAR_ingestion_lambda_s3_bucket must be set in Buildkite.}"
      just package-ingestion
      object_key="lambdas/ingestion/$${BUILDKITE_COMMIT}.zip"
      object_version="$$(aws s3api put-object \
        --bucket "$${TF_VAR_ingestion_lambda_s3_bucket}" \
        --key "$${object_key}" \
        --body dist/ingestion.zip \
        --query VersionId \
        --output text)"
      test "$${object_version}" != "None"
      printf 'export TF_VAR_ingestion_lambda_s3_key=%s\nexport TF_VAR_ingestion_lambda_s3_object_version=%s\n' "$${object_key}" "$${object_version}" > ingestion-artifact.env
      buildkite-agent annotate "### Ingestion Lambda\n\nPublished \`$${object_key}\` at S3 object version \`$${object_version}\`." --style success --context ingestion-deployment
    artifact_paths:
      - ingestion-artifact.env
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: $CI_S3_PUBLISH_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    timeout_in_minutes: 10

  - block: ":terraform: Apply"
    key: terraform-apply-approval
    depends_on: publish-ingestion

  - label: ":terraform: Apply"
    key: terraform-apply
    depends_on: terraform-apply-approval
    command: |
      : "$${TF_STATE_BUCKET:?TF_STATE_BUCKET must be set in Buildkite.}"
      buildkite-agent artifact download ingestion-artifact.env .
      . ./ingestion-artifact.env
      just terraform-init
      terraform -chdir=infra apply -auto-approve
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: $TERRAFORM_APPLY_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    timeout_in_minutes: 15
YAML
