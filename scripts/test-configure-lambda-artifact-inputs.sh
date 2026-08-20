#!/usr/bin/env bash
set -euo pipefail

temporary_directory="$(mktemp -d)"
trap 'rm -rf "$temporary_directory"' EXIT

cat >"$temporary_directory/aws" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

case "$*" in
  *"lambdas/ingestion/latest.zip"*) printf 'ingestion-version\n' ;;
  *"lambdas/matching/latest.zip"*) exit 254 ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$temporary_directory/aws"

env \
  PATH="$temporary_directory:$PATH" \
  LAMBDA_ARTIFACTS_BUCKET="shared-artifacts" \
  bash -c '
    source scripts/configure-lambda-artifact-inputs.sh
    test "$TF_VAR_ingestion_lambda_s3_key" = "lambdas/ingestion/latest.zip"
    test "$TF_VAR_ingestion_lambda_s3_object_version" = "ingestion-version"
    test "$TF_VAR_matching_lambda_s3_key" = "lambdas/matching/latest.zip"
    test -z "${TF_VAR_matching_lambda_s3_object_version:-}"
  '
