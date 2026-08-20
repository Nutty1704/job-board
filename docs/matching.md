# Matching worker

The matching Lambda consumes the versioned ingestion event documented in
`apps/README.md`. DynamoDB stores one record per `(source, source_job_id)`.
Once a job reaches `scored` or `qualified`, later deliveries are acknowledged
without rescoring. Jobs rejected by hard filters are dropped without storage,
so a later duplicate is evaluated again. Updating the profile affects only
previously scored source job IDs.

After Terraform applies, upload this JSON as `current.json` to the
`matching_profile_bucket_name` output. The bucket is private and versioned.

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
