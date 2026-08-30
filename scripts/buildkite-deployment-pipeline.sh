#!/usr/bin/env bash
set -euo pipefail

changed_files="$(git diff --name-only "${BUILDKITE_COMMIT}^" "$BUILDKITE_COMMIT")"

worker_changed() {
  local worker="$1"

  if grep -qx 'Justfile' <<<"$changed_files"; then
    return 0
  fi

  grep -q "^apps/${worker}/" <<<"$changed_files"
}

for worker in ingestion matching resume dashboard; do
  worker_changed "$worker" || continue

  case "$worker" in
    ingestion) display_name="Ingestion" ;;
    matching) display_name="Matching" ;;
    resume) display_name="Resume" ;;
    dashboard) display_name="Dashboard API" ;;
  esac
  buildkite-agent annotate "### ${display_name} Lambda\n\nApprove publishing the main commit to \`lambdas/${worker}/latest.zip\` and its immutable commit-keyed rollback copy." --style warning --context "${worker}-deployment"
done

publish_steps=""
plan_dependencies="      - prepare-deployment"
artifact_downloads=""
for worker in ingestion matching resume dashboard; do
  worker_changed "$worker" || continue

  publish_steps+="
  - block: \":package: Publish ${worker} Lambda\"
    key: publish-${worker}-approval
    depends_on: prepare-deployment

  - label: \":package: Publish ${worker} Lambda\"
    key: publish-${worker}
    depends_on: publish-${worker}-approval
    command: |
      source scripts/configure-lambda-artifact-bucket.sh
      : \"\$\${TF_VAR_${worker}_lambda_s3_bucket:?TF_VAR_${worker}_lambda_s3_bucket must be set in Buildkite.}\"
      if [ \"${worker}\" = \"dashboard\" ]; then
        npm ci --prefix apps/dashboard
      fi
      just package-${worker}
      latest_key=\"lambdas/${worker}/latest.zip\"
      commit_key=\"lambdas/${worker}/\$\${BUILDKITE_COMMIT}.zip\"
      latest_version=\"\$\$(aws s3api put-object --bucket \"\$\${TF_VAR_${worker}_lambda_s3_bucket}\" --key \"\$\${latest_key}\" --body dist/${worker}.zip --query VersionId --output text)\"
      aws s3api put-object --bucket \"\$\${TF_VAR_${worker}_lambda_s3_bucket}\" --key \"\$\${commit_key}\" --body dist/${worker}.zip >/dev/null
      test \"\$\${latest_version}\" != \"None\"
      printf 'export TF_VAR_${worker}_lambda_s3_key=%s\\nexport TF_VAR_${worker}_lambda_s3_object_version=%s\\n' \"\$\${latest_key}\" \"\$\${latest_version}\" > ${worker}-artifact.env
    artifact_paths:
      - ${worker}-artifact.env
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: \$CI_S3_PUBLISH_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    timeout_in_minutes: 10
"
  plan_dependencies+=$'\n      - publish-'"$worker"
  artifact_downloads+="      buildkite-agent artifact download ${worker}-artifact.env .
      . ./${worker}-artifact.env
"
done

cat <<YAML | buildkite-agent pipeline upload
steps:${publish_steps}
  - label: ":terraform: Plan"
    key: terraform-plan
    depends_on:
${plan_dependencies}
    command: |
      : "\$\${TF_STATE_BUCKET:?TF_STATE_BUCKET must be set in Buildkite.}"
      source scripts/configure-lambda-artifact-bucket.sh
      source scripts/configure-lambda-artifact-inputs.sh
${artifact_downloads}      just terraform-init
      terraform -chdir=infra plan -lock-timeout=5m -out=deployment.tfplan
      terraform -chdir=infra show -no-color deployment.tfplan > deployment-terraform-plan.txt
    artifact_paths:
      - infra/deployment.tfplan
      - infra/deployment-terraform-plan.txt
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: \$TERRAFORM_PLAN_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    concurrency_group: job-board-main-terraform
    concurrency: 1
    timeout_in_minutes: 10

  - block: ":terraform: Apply"
    key: terraform-apply-approval
    depends_on:
      - terraform-plan

  - label: ":terraform: Apply"
    key: terraform-apply
    depends_on: terraform-apply-approval
    command: |
      source scripts/configure-lambda-artifact-bucket.sh
      : "\$\${TF_STATE_BUCKET:?TF_STATE_BUCKET must be set in Buildkite.}"
      source scripts/configure-lambda-artifact-inputs.sh
${artifact_downloads}      buildkite-agent artifact download infra/deployment.tfplan .
      just terraform-init
      terraform -chdir=infra apply -lock-timeout=5m -auto-approve deployment.tfplan
    plugins:
      - aws-assume-role-with-web-identity#v1.2.0:
          role-arn: \$TERRAFORM_APPLY_ROLE_ARN
          session-tags:
            - organization_slug
            - pipeline_slug
            - build_branch
    concurrency_group: job-board-main-terraform
    concurrency: 1
    timeout_in_minutes: 15
YAML
