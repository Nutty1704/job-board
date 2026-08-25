# Apps

Deployable applications and workers live here.

## Ingestion Lambda

`ingestion/job_ingestion.py` is a dependency-free Python 3.12 Lambda handler
for Adzuna. It reads its credentials from Secrets Manager, fetches page 1 of
the configured Australian search, normalizes each result, and sends one
message per job to `jobs-to-score`.

Run the fixture-driven unit tests and produce the deployment ZIP from the
repository root:

```sh
just test-ingestion
just package-ingestion
```

The package command writes `dist/ingestion.zip`. It does not call Adzuna or
AWS.

### Queue message contract

Messages are compact JSON with `schema_version: 1` and this shape (fields in
`job`, `source_url`, and `raw` are omitted when unavailable):

```json
{
  "schema_version": 1,
  "source": "adzuna",
  "source_job_id": "123456",
  "source_url": "https://...",
  "ingested_at": "2026-08-18T00:00:00Z",
  "search": {
    "country": "au",
    "location": "Sydney",
    "query": "software engineer",
    "page": 1
  },
  "job": {
    "title": "...",
    "description": "...",
    "company": { "display_name": "..." },
    "location": { "display_name": "...", "area": ["..."] },
    "category": { "tag": "...", "label": "..." },
    "contract_type": "...",
    "contract_time": "...",
    "salary": { "min": 0, "max": 0, "currency": "AUD", "is_predicted": false },
    "source_created_at": "...",
    "latitude": 0,
    "longitude": 0
  },
  "raw": {}
}
```

The function sends up to ten messages per SQS request. A failed batch entry
fails the invocation, so delivery is at least once: downstream consumers must
deduplicate using `source` and `source_job_id`. To remain under SQS's 256 KB
limit, an oversized `raw` object is removed and the normalized event is still
published; an oversized normalized event fails the invocation.

## Matching Lambda

`matching/job_matching.py` consumes `jobs-to-score`, records each source job
once in DynamoDB, applies the profile's hard filters, and uses OpenAI
`gpt-5.6-luna` to classify job-skill evidence. Deterministic code combines
weighted skill fit with role alignment; jobs at or above the profile threshold
are sent to `high-match-jobs`.

```sh
just test-matching
just package-matching
```

The output ZIP is `dist/matching.zip`. The worker uses only the standard
library and Lambda's `boto3`; tests use fakes and never contact AWS or OpenAI.
The `high-match-jobs` consumer must tolerate duplicates: publishing happens
after DynamoDB persistence and SQS delivery is at least once.

## Resume Lambda

`resume/job_resume.py` consumes qualified matching records from
`high-match-jobs` and produces one DOCX resume per versioned profile/template
pair. It uses a DynamoDB processing lease keyed by the source job and input
versions, so duplicate SQS deliveries do not repeat the model call.

```sh
just test-resume
just package-resume
```

Before deploying, populate the ignored `local/matching-profile.json` with the
`resume` source-bullet pool and upload it to `matching/current.json`; upload
the Jinja-enabled `local/resume-template.docx` to
`resumes/templates/current.docx`. Both project-data objects must retain S3
versions. Generated documents are written as `resumes/<job_id>.docx` and expire
after 21 days.
