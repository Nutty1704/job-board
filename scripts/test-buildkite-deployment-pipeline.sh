#!/usr/bin/env bash
set -euo pipefail

temporary_directory="$(mktemp -d)"
trap 'rm -rf "$temporary_directory"' EXIT

cat >"$temporary_directory/buildkite-agent" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$1 $2" == "pipeline upload" ]]; then
  cat >"$PIPELINE_OUTPUT"
fi
EOF
chmod +x "$temporary_directory/buildkite-agent"

PIPELINE_OUTPUT="$temporary_directory/pipeline.yml" \
PATH="$temporary_directory:$PATH" \
BUILDKITE_COMMIT="0123456789abcdef" \
bash scripts/buildkite-deployment-pipeline.sh

grep -F 'key: publish-ingestion' "$temporary_directory/pipeline.yml"
grep -F 'key: publish-matching' "$temporary_directory/pipeline.yml"
grep -F 'latest_key="lambdas/ingestion/latest.zip"' "$temporary_directory/pipeline.yml"
grep -F 'commit_key="lambdas/matching/$${BUILDKITE_COMMIT}.zip"' "$temporary_directory/pipeline.yml"
grep -F 'key: terraform-plan' "$temporary_directory/pipeline.yml"
grep -F 'terraform -chdir=infra apply -auto-approve deployment.tfplan' "$temporary_directory/pipeline.yml"
