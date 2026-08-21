"""SQS worker that filters and scores normalized job-listing events."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


COMPLETED_STATUSES = {"filtered_out", "scored", "qualified"}
EXPERIENCE_PATTERN = re.compile(
    r"(?i)(?:requires?|required|minimum|at least)\s*(?:of\s*)?(\d+)\+?\s+years?(?:\s+of)?\s+professional\s+experience"
)
TRAILING_EXPERIENCE_PATTERN = re.compile(
    r"(?i)(\d+)\+?\s+years?(?:\s+of)?\s+professional\s+experience[^.]{0,80}\b(?:required|minimum|at least)\b"
)


@dataclass(frozen=True)
class Config:
    table_name: str
    profile_bucket: str
    profile_key: str
    profile_region: str
    openai_parameter_name: str
    output_queue_url: str
    model: str = "text-embedding-3-small"
    lease_seconds: int = 300
    threshold_override: int | None = None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "Config":
        defaults = {
            "JOB_MATCHES_TABLE": "job-matches",
            "MATCHING_PROFILE_BUCKET": "profiles",
            "MATCHING_PROFILE_KEY": "matching/current.json",
            "MATCHING_PROFILE_REGION": "ap-southeast-2",
            "OPENAI_PARAMETER_NAME": "openai",
            "HIGH_MATCH_JOBS_QUEUE_URL": "high-match-jobs",
        }
        values = {key: environment.get(key, default).strip() for key, default in defaults.items()}
        lease_seconds = int(environment.get("MATCHING_LEASE_SECONDS", "300"))
        threshold = environment.get("MATCHING_SCORE_THRESHOLD", "").strip()
        if lease_seconds < 1:
            raise ValueError("MATCHING_LEASE_SECONDS must be positive")
        return cls(
            table_name=values["JOB_MATCHES_TABLE"], profile_bucket=values["MATCHING_PROFILE_BUCKET"],
            profile_key=values["MATCHING_PROFILE_KEY"], profile_region=values["MATCHING_PROFILE_REGION"],
            openai_parameter_name=values["OPENAI_PARAMETER_NAME"], output_queue_url=values["HIGH_MATCH_JOBS_QUEUE_URL"],
            model=environment.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            lease_seconds=lease_seconds, threshold_override=int(threshold) if threshold else None,
        )


@dataclass(frozen=True)
class Profile:
    version: str
    candidate_summary: str
    required_skills_any: tuple[str, ...]
    allowed_locations: tuple[str, ...]
    excluded_phrases: tuple[str, ...]
    max_required_experience_years: int
    qualified_score_threshold: int


def parse_profile(contents: bytes) -> Profile:
    try:
        value = json.loads(contents.decode("utf-8"))
        filters = value["filters"]
        profile = Profile(
            version=_required_string(value, "version"), candidate_summary=_required_string(value, "candidate_summary"),
            required_skills_any=_string_tuple(filters, "required_skills_any"),
            allowed_locations=_string_tuple(filters, "allowed_locations"),
            excluded_phrases=_string_tuple(filters, "excluded_phrases"),
            max_required_experience_years=int(filters["max_required_experience_years"]),
            qualified_score_threshold=int(value["qualified_score_threshold"]),
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Matching profile has an invalid format") from error
    if profile.max_required_experience_years < 0 or not 0 <= profile.qualified_score_threshold <= 100:
        raise ValueError("Matching profile has invalid numeric limits")
    return profile


def validate_ingestion_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Event must use schema_version 1")
    for key in ("source", "source_job_id", "ingested_at"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"Event requires a non-empty {key}")
    if not isinstance(value.get("job"), dict):
        raise ValueError("Event requires a job object")
    return value


def hard_filter(event: Mapping[str, Any], profile: Profile) -> str | None:
    job = event["job"]
    description = job.get("description")
    if not isinstance(description, str) or not description.strip():
        return "missing_description"
    text = description.casefold()
    location = _location_text(job).casefold()
    if not any(allowed.casefold() in location for allowed in profile.allowed_locations):
        return "location_not_allowed"
    if any(phrase.casefold() in text for phrase in profile.excluded_phrases):
        return "excluded_phrase"
    if not any(skill.casefold() in text for skill in profile.required_skills_any):
        return "required_skill_missing"
    required_years = [int(match.group(1)) for match in EXPERIENCE_PATTERN.finditer(description)]
    required_years.extend(int(match.group(1)) for match in TRAILING_EXPERIENCE_PATTERN.finditer(description))
    if any(years > profile.max_required_experience_years for years in required_years):
        return "experience_requirement_exceeds_limit"
    return None


def build_profile_summary(profile: Profile) -> str:
    return f"Candidate profile:\n{profile.candidate_summary}"


def build_job_summary(event: Mapping[str, Any]) -> str:
    job = event["job"]
    company = job.get("company", {}).get("display_name", "") if isinstance(job.get("company"), dict) else ""
    return "\n".join(part for part in (
        f"Title: {job.get('title', '')}", f"Company: {company}", f"Location: {_location_text(job)}",
        f"Description: {job.get('description', '')}",
    ) if part.strip())


def parse_embeddings(response: Any, expected_count: int) -> list[list[float]]:
    if not isinstance(response, dict) or not isinstance(response.get("data"), list) or len(response["data"]) != expected_count:
        raise ValueError("OpenAI response must contain one embedding per input")
    vectors = []
    for item in response["data"]:
        vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vector, list) or not vector or not all(isinstance(number, (int, float)) for number in vector):
            raise ValueError("OpenAI response contains an invalid embedding")
        vectors.append([float(number) for number in vector])
    if len({len(vector) for vector in vectors}) != 1:
        raise ValueError("OpenAI embeddings must have equal dimensions")
    return vectors


def match_score(profile_embedding: list[float], job_embedding: list[float]) -> tuple[float, int]:
    magnitude = math.sqrt(sum(value * value for value in profile_embedding)) * math.sqrt(sum(value * value for value in job_embedding))
    cosine = sum(left * right for left, right in zip(profile_embedding, job_embedding)) / magnitude if magnitude else 0.0
    similarity = max(0.0, cosine)
    return similarity, round(100 * similarity)


class Matcher:
    def __init__(self, config: Config, s3: Any, parameter_store: Any, table: Any, sqs: Any, embeddings_request: Callable[[str, str, list[str]], Any]):
        self.config, self.s3, self.parameter_store, self.table, self.sqs, self.embeddings_request = config, s3, parameter_store, table, sqs, embeddings_request

    def process(self, event: dict[str, Any]) -> str:
        return self.process_many([event])[0]

    def process_many(self, events: list[dict[str, Any]]) -> list[str]:
        results: list[str | None] = [None] * len(events)
        candidates: list[dict[str, Any]] = []
        for index, event in enumerate(events):
            validate_ingestion_event(event)
            candidates.append({"index": index, "event": event})
        if not candidates:
            return []
        profile, profile_version_id = self._load_profile()
        leased: list[dict[str, Any]] = []
        for item in candidates:
            if hard_filter(item["event"], profile):
                results[item["index"]] = "filtered_out"
                continue
            event = item["event"]
            lease = self._acquire_lease(event)
            if not lease:
                results[item["index"]] = "duplicate"
            else:
                leased.append(item)
        if not leased:
            return [result or "duplicate" for result in results]
        if leased:
            api_key = self._api_key()
            vectors = parse_embeddings(self.embeddings_request(api_key, self.config.model, [build_profile_summary(profile)] + [build_job_summary(item["event"]) for item in leased]), len(leased) + 1)
            for item, vector in zip(leased, vectors[1:]):
                similarity, score = match_score(vectors[0], vector)
                threshold = self.config.threshold_override if self.config.threshold_override is not None else profile.qualified_score_threshold
                status = "qualified" if score >= threshold else "scored"
                record = {"status": status, "raw_similarity": similarity, "match_score": score, "profile_version": profile.version, "profile_s3_version": profile_version_id, "embedding_model": self.config.model}
                stored = self._persist(item["event"], record)
                if status == "qualified":
                    self.sqs.send_message(QueueUrl=self.config.output_queue_url, MessageBody=json.dumps(stored, separators=(",", ":"), ensure_ascii=False))
                results[item["index"]] = status
        return [result or "duplicate" for result in results]

    def _acquire_lease(self, event: Mapping[str, Any]) -> bool:
        now = datetime.now(timezone.utc)
        item = {"source": event["source"], "source_job_id": event["source_job_id"], "status": "processing", "lease_expires_at": (now + timedelta(seconds=self.config.lease_seconds)).isoformat(), "started_at": now.isoformat()}
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(#source) OR (#status = :processing AND lease_expires_at < :now)", ExpressionAttributeNames={"#source": "source", "#status": "status"}, ExpressionAttributeValues={":processing": "processing", ":now": now.isoformat()})
            return True
        except Exception as error:
            if _is_conditional_failure(error):
                return False
            raise

    def _load_profile(self) -> tuple[Profile, str | None]:
        response = self.s3.get_object(Bucket=self.config.profile_bucket, Key=self.config.profile_key)
        return parse_profile(response["Body"].read()), response.get("VersionId")

    def _api_key(self) -> str:
        parameter = self.parameter_store.get_parameter(Name=self.config.openai_parameter_name, WithDecryption=True)
        secret = parameter.get("Parameter", {}).get("Value")
        try:
            key = json.loads(secret)["api_key"]
        except (TypeError, KeyError, json.JSONDecodeError) as error:
            raise ValueError("OpenAI parameter must contain api_key") from error
        if not isinstance(key, str) or not key.strip():
            raise ValueError("OpenAI parameter must contain api_key")
        return key

    def _persist(self, event: Mapping[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        stored_event = dict(event)
        stored_event.pop("raw", None)
        stored = {"source": event["source"], "source_job_id": event["source_job_id"], "job_event": stored_event, **record, "processed_at": datetime.now(timezone.utc).isoformat()}
        self.table.put_item(Item=stored)
        return stored


def openai_embeddings(api_key: str, model: str, inputs: list[str]) -> dict[str, Any]:
    request = Request("https://api.openai.com/v1/embeddings", data=json.dumps({"model": model, "input": inputs}).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:  # nosec B310 - fixed OpenAI URL
            if not 200 <= getattr(response, "status", response.getcode()) < 300:
                raise RuntimeError("OpenAI embeddings request failed")
            return json.loads(response.read().decode())
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("OpenAI embeddings request failed") from error


def process_sqs_batch(event: Any, matcher: Matcher) -> dict[str, list[dict[str, str]]]:
    failures, valid, ids = [], [], []
    if not isinstance(event, dict) or not isinstance(event.get("Records"), list):
        raise ValueError("SQS event requires Records")
    for record in event["Records"]:
        message_id = record.get("messageId") if isinstance(record, dict) else None
        try:
            if not isinstance(message_id, str) or not isinstance(record.get("body"), str):
                raise ValueError("Invalid SQS record")
            valid.append(validate_ingestion_event(json.loads(record["body"])))
            ids.append(message_id)
        except (TypeError, ValueError, json.JSONDecodeError):
            if message_id:
                failures.append({"itemIdentifier": message_id})
    try:
        matcher.process_many(valid)
    except Exception:
        logger.exception("Failed matching SQS batch for message IDs: %s", ids)
        failures.extend({"itemIdentifier": message_id} for message_id in ids)
    return {"batchItemFailures": failures}


def lambda_handler(event: Any, context: Any) -> dict[str, list[dict[str, str]]]:
    del context
    import boto3
    config = Config.from_environment(os.environ)
    matcher = Matcher(config, boto3.client("s3", region_name=config.profile_region), boto3.client("ssm"), boto3.resource("dynamodb").Table(config.table_name), boto3.client("sqs"), openai_embeddings)
    return process_sqs_batch(event, matcher)


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item.strip():
        raise ValueError(key)
    return item.strip()


def _string_tuple(value: Mapping[str, Any], key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or not items or not all(isinstance(item, str) and item.strip() for item in items):
        raise ValueError(key)
    return tuple(item.strip() for item in items)


def _location_text(job: Mapping[str, Any]) -> str:
    location = job.get("location")
    if not isinstance(location, dict):
        return ""
    return " ".join(str(item) for item in [location.get("display_name", ""), *location.get("area", [])] if isinstance(item, str))


def _is_conditional_failure(error: Exception) -> bool:
    return getattr(error, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException"
