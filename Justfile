default:
    @just --list

# Run the dependency-free Lambda ingestion unit tests.
test-ingestion:
    python3 -m unittest discover -s apps/ingestion/tests -v

# Run the dependency-free Lambda matching unit tests.
test-matching:
    python3 -m unittest discover -s apps/matching/tests -v

# Run the dependency-free Lambda resume unit tests.
test-resume:
    python3 -m unittest discover -s apps/resume/tests -v

# Package the Lambda handler for upload to the versioned artifact bucket.
package-ingestion:
    python3 -c 'from pathlib import Path; import zipfile; output = Path("dist/ingestion.zip"); output.parent.mkdir(exist_ok=True); archive = zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED); archive.write("apps/ingestion/job_ingestion.py", "job_ingestion.py"); archive.close()'

# Package the matching Lambda handler for upload to the versioned artifact bucket.
package-matching:
    python3 -c 'from pathlib import Path; import zipfile; output = Path("dist/matching.zip"); output.parent.mkdir(exist_ok=True); archive = zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED); archive.write("apps/matching/job_matching.py", "job_matching.py"); archive.write("apps/matching/config.py", "config.py"); archive.close()'

# Package the resume handler and its DOCX templating dependency for Lambda.
package-resume:
    rm -rf build/resume
    python3 -m pip install --disable-pip-version-check -q -r apps/resume/requirements.txt -t build/resume
    cp apps/resume/job_resume.py build/resume/job_resume.py
    python3 -c 'from pathlib import Path; import zipfile; output = Path("dist/resume.zip"); output.parent.mkdir(exist_ok=True); archive = zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED); [archive.write(path, path.relative_to("build/resume")) for path in Path("build/resume").rglob("*") if path.is_file()]; archive.close()'

# Run Trunk's configured linters and format checks.
trunk-check:
    if [ -x local/bin/trunk ]; then local/bin/trunk check; else trunk check; fi

# Apply formatting fixes supported by Trunk.
trunk-fmt:
    if [ -x local/bin/trunk ]; then local/bin/trunk fmt; else trunk fmt; fi

# Update Trunk and its enabled tool versions.
trunk-upgrade:
    if [ -x local/bin/trunk ]; then local/bin/trunk upgrade; else trunk upgrade; fi

# Initialize Terraform providers and the configured state backend. Set
# TF_STATE_BUCKET to the bootstrap stack's terraform_state_bucket_name output.
terraform-init:
    : "${TF_STATE_BUCKET:?Set TF_STATE_BUCKET to the Terraform state bucket name.}"
    terraform -chdir=infra init -backend-config="bucket=$TF_STATE_BUCKET"

# Format all Terraform configuration files in place.
terraform-fmt:
    terraform -chdir=infra fmt

# Check Terraform formatting without modifying files.
terraform-fmt-check:
    terraform -chdir=infra fmt -check

# Validate Terraform syntax and provider configuration locally.
terraform-validate:
    terraform -chdir=infra validate

# Show the infrastructure change set. Requires an untracked infra/terraform.tfvars.
terraform-plan:
    terraform -chdir=infra plan

# Apply the reviewed infrastructure change set. Terraform will ask for confirmation.
terraform-apply:
    terraform -chdir=infra apply

# Display values exported by the currently applied infrastructure stack.
terraform-output:
    terraform -chdir=infra output

# Initialize the bootstrap stack with local state. Use only for its first
# apply, before the state bucket exists.
bootstrap-init-local:
    terraform -chdir=infra/bootstrap init -reconfigure

# Initialize the bootstrap stack using its remote state. Set TF_STATE_BUCKET
# to the bootstrap stack's terraform_state_bucket_name output.
bootstrap-init:
    : "${TF_STATE_BUCKET:?Set TF_STATE_BUCKET to the Terraform state bucket name.}"
    test -f infra/bootstrap/backend.tf
    terraform -chdir=infra/bootstrap init -backend-config="bucket=$TF_STATE_BUCKET"

# Copy the one-time local bootstrap state to the state bucket. Run after the
# first bootstrap apply, then use bootstrap-init for all future bootstrap work.
bootstrap-migrate-state:
    : "${TF_STATE_BUCKET:?Set TF_STATE_BUCKET to the Terraform state bucket name.}"
    test -f infra/bootstrap/backend.tf
    terraform -chdir=infra/bootstrap init -migrate-state -backend-config="bucket=$TF_STATE_BUCKET"

bootstrap-fmt:
    terraform -chdir=infra/bootstrap fmt

bootstrap-fmt-check:
    terraform -chdir=infra/bootstrap fmt -check

bootstrap-validate-local:
    terraform -chdir=infra/bootstrap validate

bootstrap-plan:
    terraform -chdir=infra/bootstrap plan

bootstrap-apply:
    terraform -chdir=infra/bootstrap apply

bootstrap-output:
    terraform -chdir=infra/bootstrap output
