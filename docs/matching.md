# Matching worker

The matching Lambda consumes the versioned ingestion event documented in
`apps/README.md`. DynamoDB stores one record per `(source, source_job_id)`.
Once a job reaches `scored` or `qualified`, later deliveries are acknowledged
without rescoring. Jobs rejected by hard filters are dropped without storage,
so a later duplicate is evaluated again. Updating the profile affects only
previously scored source job IDs.

After Terraform applies, upload this JSON to `matching/current.json` in the
`project_data_bucket_name` output. The project-data bucket is private and
versioned; other project files use purpose-based prefixes such as `jobs/` and
`resumes/`.

This prerequisite deployment does not yet connect the matching Lambda to SQS.
Upload the profile and populate the OpenAI parameter before applying the
follow-up consumer deployment; that later deployment starts processing the
messages already waiting in `jobs-to-score`.

```json
{
  "version": "2026-08-20",
  "candidate_summary": "Experience, education, skills, target roles, and preferences in plain text.",
  "filters": {
    "required_skills_any": ["python", "aws"],
    "allowed_locations": ["sydney", "melbourne"],
    "excluded_phrases": ["security clearance required"],
    "max_required_experience_years": 2
  },
  "qualified_score_threshold": 80
}
```

For example:

```sh
aws s3 cp matching-profile.json \
  "s3://$(terraform -chdir=infra output -raw project_data_bucket_name)/matching/current.json"
```

## Migrating an existing profile bucket

Before applying this change, inspect remote Terraform state:

```sh
terraform -chdir=infra state list | grep aws_s3_bucket.matching_profiles
```

No output means the previous random-suffix bucket was never deployed and a
normal apply can create the exact `job-board-personal` bucket. If it is
present, create the new bucket and its settings with targeted apply first,
copy the existing `current.json` to `matching/current.json`, then run the
normal apply to retire the old bucket:

```sh
terraform -chdir=infra apply \
  -target=aws_s3_bucket.project_data \
  -target=aws_s3_bucket_versioning.project_data \
  -target=aws_s3_bucket_server_side_encryption_configuration.project_data \
  -target=aws_s3_bucket_public_access_block.project_data \
  -target=aws_s3_bucket_lifecycle_configuration.project_data

OLD_PROFILE_BUCKET="$(terraform -chdir=infra state show -no-color aws_s3_bucket.matching_profiles | sed -n 's/^ *bucket *= *"\(.*\)"$/\1/p')"
aws s3 cp "s3://${OLD_PROFILE_BUCKET}/current.json" \
  "s3://job-board-personal/matching/current.json"

terraform -chdir=infra apply
```

Terraform intentionally uses the exact name `job-board-personal`; if another
AWS account owns it, the apply fails rather than selecting a suffixed name.

The worker rejects jobs with no description, an unallowed location, an
excluded phrase, no required skill, or explicit required/minimum/at-least
professional experience over the configured limit. Preferred experience does
not reject a job. The score is a non-negative cosine similarity scaled to 100;
it is a ranking signal, not a calibrated percentage.

After Terraform applies, replace the placeholder in the
`openai_parameter_name` standard SSM SecureString with `{"api_key":"…"}`.
For example:

```sh
aws ssm put-parameter \
  --name "$(terraform -chdir=infra output -raw openai_parameter_name)" \
  --type SecureString \
  --value '{"api_key":"…"}' \
  --overwrite
```

On `main`, Buildkite tests both Lambdas, manually gates
any changed Lambda artifact publish, records the resulting S3 object version,
and then manually gates Terraform apply. Infrastructure-only applies retain
the previously configured artifact key and version.
