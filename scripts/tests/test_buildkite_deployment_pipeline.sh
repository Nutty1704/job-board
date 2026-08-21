#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fake_bin="$(mktemp -d)"
generated_pipeline="$(mktemp)"
trap 'rm -rf "$fake_bin" "$generated_pipeline"' EXIT

cat >"$fake_bin/buildkite-agent" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

case "$1" in
  annotate) exit 0 ;;
  pipeline)
    test "$2" = "upload"
    cat >"$BUILDKITE_TEST_PIPELINE_OUTPUT"
    ;;
  *)
    echo "unexpected buildkite-agent command: $*" >&2
    exit 1
    ;;
esac
SCRIPT
chmod +x "$fake_bin/buildkite-agent"

cat >"$fake_bin/git" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

test "$1" = "diff"
test "$2" = "--name-only"
printf '%s\n' "$BUILDKITE_TEST_CHANGED_FILES"
SCRIPT
chmod +x "$fake_bin/git"

generate_pipeline() {
  : >"$generated_pipeline"
  PATH="$fake_bin:$PATH" \
  BUILDKITE_COMMIT="$(git -C "$repo_root" rev-parse HEAD)" \
  BUILDKITE_TEST_CHANGED_FILES="$1" \
  BUILDKITE_TEST_PIPELINE_OUTPUT="$generated_pipeline" \
  bash "$repo_root/scripts/buildkite-deployment-pipeline.sh"
}

assert_publish_steps() {
  local expected_ingestion="$1"
  local expected_matching="$2"
  local actual_ingestion=false
  local actual_matching=false

  if grep -q 'key: publish-ingestion' "$generated_pipeline"; then
    actual_ingestion=true
  fi
  if [[ "$actual_ingestion" != "$expected_ingestion" ]]; then
    echo "unexpected ingestion publish step" >&2
    exit 1
  fi

  if grep -q 'key: publish-matching' "$generated_pipeline"; then
    actual_matching=true
  fi
  if [[ "$actual_matching" != "$expected_matching" ]]; then
    echo "unexpected matching publish step" >&2
    exit 1
  fi
}

generate_pipeline "infra/matching.tf"
assert_publish_steps false false
grep -q 'key: terraform-plan' "$generated_pipeline"

generate_pipeline "apps/ingestion/job_ingestion.py"
assert_publish_steps true false

generate_pipeline "apps/matching/job_matching.py"
assert_publish_steps false true

generate_pipeline "Justfile"
assert_publish_steps true true
