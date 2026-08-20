# Job Board MVP

This is a personal project: a centralized job board that collects relevant
software-engineering roles from a small number of job portals. It is intended
both to support the owner's job search and to demonstrate practical system
design and implementation skills.

## Current Goal

Build a working prototype that can ingest job listings, normalize them, and
store them in PostgreSQL. The initial focus is software-engineer roles in
Sydney, with Melbourne and additional sources to follow after the basic flow
works.

The first source is SerpApi's Google Jobs API. Routine development uses a
recorded sample response so tests and local runs do not consume API credits.

## Current Scope

- Python ingestion command intended to later run on a schedule.
- Config-driven search parameters and source mode.
- Local PostgreSQL storage, migrations, raw-response retention, and
  idempotent upserts.
- A small CLI and local Docker workflow for running the prototype.

## Out Of Scope For Now

- Frontend, user accounts, authentication, and multi-user support.
- AWS deployment, Lambda configuration, Terraform, S3, or hosted databases.
- Application tracking, ranking, notifications, resumes, and other job-search
  workflow features.
- Production-scale observability, reliability systems, or extensive defensive
  abstractions.

## Engineering Approach

Prefer clear, direct code over production-grade ceremony. This is an MVP: add
structure and tests where they protect the ingestion flow, data integrity, or a
real regression, but do not introduce abstractions or validation suites merely
for hypothetical future scale.

Keep changes narrow and working end to end. Preserve the sample-first workflow
and do not make live SerpApi calls from automated tests. Do not commit secrets
or local runtime artifacts.

## Repository Conventions

- `apps/ingestion/` contains the Python ingestion application.
- `local/` is ignored and holds developer-only Docker, configuration, samples,
  and raw-data files.
- The repository root `Justfile` contains shared project commands; `local/`
  has developer-only commands.
- `docs/` contains architecture and decision records. Planning artifacts under
  `docs/superpowers/` are local and ignored.
- Project data (jobs, profiles, resumes, and future user-facing files) belongs
  in the project-data S3 bucket under purpose-based prefixes such as
  `matching/`, `jobs/`, and `resumes/`. Terraform state and Lambda deployment
  artifacts remain in their dedicated buckets.
