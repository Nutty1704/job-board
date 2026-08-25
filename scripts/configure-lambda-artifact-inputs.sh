#!/usr/bin/env bash
set -euo pipefail

: "${LAMBDA_ARTIFACTS_BUCKET:?LAMBDA_ARTIFACTS_BUCKET must be set in Buildkite.}"

for worker in ingestion matching resume; do
  key="lambdas/${worker}/latest.zip"
  version="$(aws s3api head-object \
    --bucket "$LAMBDA_ARTIFACTS_BUCKET" \
    --key "$key" \
    --query VersionId \
    --output text 2>/dev/null || true)"

  export "TF_VAR_${worker}_lambda_s3_key=$key"
  if [[ -n "$version" && "$version" != "None" ]]; then
    export "TF_VAR_${worker}_lambda_s3_object_version=$version"
  else
    unset "TF_VAR_${worker}_lambda_s3_object_version" || true
  fi
done
