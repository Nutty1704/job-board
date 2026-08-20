#!/usr/bin/env bash
set -euo pipefail

changed() {
  ! git rev-parse --verify "${BUILDKITE_COMMIT}^" >/dev/null 2>&1 || ! git diff --quiet "${BUILDKITE_COMMIT}^" "${BUILDKITE_COMMIT}" -- "$1"
}

ingestion_changed=false
matching_changed=false
changed apps/ingestion && ingestion_changed=true
changed apps/matching && matching_changed=true

for worker in ingestion matching; do
  variable="${worker}_changed"
  case "$worker" in
    ingestion) display_name="Ingestion" ;;
    matching) display_name="Matching" ;;
  esac
  if [[ "${!variable}" == true ]]; then
    message="Files under \`apps/${worker}/\` changed. Approve its artifact publish before Terraform can be applied."
    style=warning
  else
    message="No files under \`apps/${worker}/\` changed. The existing artifact key and S3 object version remain pinned."
    style=info
  fi
  buildkite-agent annotate "### ${display_name} Lambda\n\n${message}" --style "$style" --context "${worker}-deployment"
done

publish_steps=""
apply_dependencies="      - prepare-deployment"
apply_downloads=""
for worker in ingestion matching; do
  variable="${worker}_changed"
  if [[ "${!variable}" != true ]]; then
    continue
  fi
  publish_steps+="
  - block: \":package: Publish ${worker} Lambda\"
    key: publish-${worker}-approval
    depends_on: prepare-deployment

  - label: \":package: Publish ${worker} Lambda\"
    key: publish-${worker}
    depends_on: publish-${worker}-approval
    command: |
      : \"\\\$\\\${TF_VAR_${worker}_lambda_s3_bucket:?TF_VAR_${worker}_lambda_s3_bucket must be set in Buildkite.}\"
      just package-${worker}
      object_key=\"lambdas/${worker}/\\\$\\\${BUILDKITE_COMMIT}.zip\"
      object_version=\"\\\$\\\$(aws s3api put-object --bucket \"\\\$\\\${TF_VAR_${worker}_lambda_s3_bucket}\" --key \"\\\$\\\${object_key}\" --body dist/${worker}.zip --query VersionId --output text)\"
      test \"\\\$\\\${object_version}\" != \"None\"
      printf 'export TF_VAR_${worker}_lambda_s3_key=%s\\nexport TF_VAR_${worker}_lambda_s3_object_version=%s\\n' \"\\\$\\\${object_key}\" \"\\\$\\\${object_version}\" > ${worker}-artifact.env
    artifact_paths:
      - ${worker}-artifact.env
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: \\\$CI_S3_PUBLISH_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    timeout_in_minutes: 10
"
  apply_dependencies+=$'\n      - publish-'"$worker"
  apply_downloads+="      buildkite-agent artifact download ${worker}-artifact.env .
      . ./${worker}-artifact.env
"
done

cat <<YAML | buildkite-agent pipeline upload
steps:${publish_steps}
  - block: ":terraform: Apply"
    key: terraform-apply-approval
    depends_on:
${apply_dependencies}

  - label: ":terraform: Apply"
    key: terraform-apply
    depends_on: terraform-apply-approval
    command: |
      : "\$\${TF_STATE_BUCKET:?TF_STATE_BUCKET must be set in Buildkite.}"
${apply_downloads}      just terraform-init
      terraform -chdir=infra apply -auto-approve
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: \$TERRAFORM_APPLY_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    timeout_in_minutes: 15
YAML
