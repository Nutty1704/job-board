#!/usr/bin/env bash

: "${LAMBDA_ARTIFACTS_BUCKET:?LAMBDA_ARTIFACTS_BUCKET must be set in Buildkite.}"

export TF_VAR_ingestion_lambda_s3_bucket="$LAMBDA_ARTIFACTS_BUCKET"
export TF_VAR_matching_lambda_s3_bucket="$LAMBDA_ARTIFACTS_BUCKET"
export TF_VAR_resume_lambda_s3_bucket="$LAMBDA_ARTIFACTS_BUCKET"
export TF_VAR_dashboard_lambda_s3_bucket="$LAMBDA_ARTIFACTS_BUCKET"
