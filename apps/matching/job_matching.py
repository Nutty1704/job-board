"""SQS worker that filters and scores normalized job-listing events."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from config import (
    ASSESSMENT_INSTRUCTIONS,
    ASSESSMENT_SCHEMA,
    Config,
    EXPERIENCE_PATTERN,
    MAX_ASSESSMENT_WORKERS,
    OPENAI_REASONING_EFFORT,
    OPENAI_REQUEST_TIMEOUT_SECONDS,
    OPENAI_RESPONSE_ENDPOINT,
    SKILL_GROUP_WEIGHTS,
    TRAILING_EXPERIENCE_PATTERN,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Profile:
    version: str
    candidate_summary: str
    candidate_skills: tuple[str, ...]
    allowed_locations: tuple[str, ...]
    excluded_phrases: tuple[str, ...]
    max_required_experience_years: int
    qualified_score_threshold: int


@dataclass(frozen=True)
class SkillAssessment:
    skill: str
    candidate_skill: str | None
    evidence: str


@dataclass(frozen=True)
class Assessment:
    role_alignment_score: int
    required_skills: tuple[SkillAssessment, ...]
    core_skills: tuple[SkillAssessment, ...]
    preferred_skills: tuple[SkillAssessment, ...]


def parse_profile(contents: bytes) -> Profile:
    try:
        value = json.loads(contents.decode("utf-8"))
        filters = value["filters"]
        profile = Profile(
            version=_required_string(value, "version"), candidate_summary=_required_string(value, "candidate_summary"),
            candidate_skills=_string_tuple(value, "candidate_skills"),
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
    required_years = [int(match.group(1)) for match in EXPERIENCE_PATTERN.finditer(description)]
    required_years.extend(int(match.group(1)) for match in TRAILING_EXPERIENCE_PATTERN.finditer(description))
    if any(years > profile.max_required_experience_years for years in required_years):
        return "experience_requirement_exceeds_limit"
    return None


def parse_openai_response(response: Any) -> dict[str, Any]:
    try:
        for output in response["output"]:
            for content in output.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    value = json.loads(content["text"])
                    if isinstance(value, dict):
                        return value
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("OpenAI response lacks structured output") from error
    raise ValueError("OpenAI response lacks structured output")


def parse_assessment(value: Any, candidate_skills: tuple[str, ...]) -> Assessment:
    if not isinstance(value, dict) or not isinstance(value.get("role_alignment_score"), int) or isinstance(value.get("role_alignment_score"), bool):
        raise ValueError("Assessment has invalid role_alignment_score")
    score = value["role_alignment_score"]
    if not 0 <= score <= 100:
        raise ValueError("Assessment has invalid role_alignment_score")
    candidate_skill_set = {item.casefold() for item in candidate_skills}
    groups: dict[str, tuple[SkillAssessment, ...]] = {}
    for group in SKILL_GROUP_WEIGHTS:
        entries = value.get(group)
        if not isinstance(entries, list):
            raise ValueError(f"Assessment has invalid {group}")
        parsed = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("skill"), str) or not entry["skill"].strip() or not isinstance(entry.get("evidence"), str) or not entry["evidence"].strip():
                raise ValueError(f"Assessment has invalid {group}")
            candidate_skill = entry.get("candidate_skill")
            if candidate_skill is not None and (not isinstance(candidate_skill, str) or candidate_skill.casefold() not in candidate_skill_set):
                raise ValueError("Assessment has invalid candidate_skill")
            parsed.append(SkillAssessment(entry["skill"].strip(), candidate_skill.casefold() if isinstance(candidate_skill, str) else None, entry["evidence"].strip()))
        groups[group] = tuple(parsed)
    return Assessment(score, groups["required_skills"], groups["core_skills"], groups["preferred_skills"])


def score_assessment(assessment: Assessment) -> tuple[int, int]:
    groups = {name: getattr(assessment, name) for name in SKILL_GROUP_WEIGHTS}
    active_weight = sum(SKILL_GROUP_WEIGHTS[name] for name, skills in groups.items() if skills)
    if not active_weight:
        return assessment.role_alignment_score, assessment.role_alignment_score
    skill_fit = sum(
        SKILL_GROUP_WEIGHTS[name] / active_weight * 100 * sum(skill.candidate_skill is not None for skill in skills) / len(skills)
        for name, skills in groups.items() if skills
    )
    skill_fit = round(skill_fit)
    return skill_fit, round(0.85 * skill_fit + 0.15 * assessment.role_alignment_score)


def dynamodb_value(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: dynamodb_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [dynamodb_value(item) for item in value]
    return value


class Matcher:
    def __init__(self, config: Config, s3: Any, parameter_store: Any, table: Any, sqs: Any, assessment_request: Callable[[str, str, Profile, Mapping[str, Any]], dict[str, Any]]):
        self.config, self.s3, self.parameter_store, self.table, self.sqs, self.assessment_request = config, s3, parameter_store, table, sqs, assessment_request

    def process(self, event: dict[str, Any]) -> str:
        results, errors = self._process_many([event])
        if errors[0] is not None:
            raise errors[0]
        return results[0] or "duplicate"

    def process_many(self, events: list[dict[str, Any]]) -> list[str | None]:
        results, _ = self._process_many(events)
        return results

    def _process_many(self, events: list[dict[str, Any]]) -> tuple[list[str | None], list[Exception | None]]:
        results: list[str | None] = [None] * len(events)
        errors: list[Exception | None] = [None] * len(events)
        for event in events:
            validate_ingestion_event(event)
        if not events:
            return results, errors
        profile, profile_version_id = self._load_profile()
        leased = []
        for index, event in enumerate(events):
            if hard_filter(event, profile):
                results[index] = "filtered_out"
            elif self._acquire_lease(event):
                leased.append((index, event))
            else:
                results[index] = "duplicate"
        if not leased:
            return results, errors
        api_key = self._api_key()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_ASSESSMENT_WORKERS, len(leased))) as executor:
            futures = {executor.submit(self.assessment_request, api_key, self.config.model, profile, event): (index, event) for index, event in leased}
            for future in concurrent.futures.as_completed(futures):
                index, event = futures[future]
                try:
                    assessment = parse_assessment(future.result(), profile.candidate_skills)
                    skill_fit, score = score_assessment(assessment)
                    threshold = self.config.threshold_override if self.config.threshold_override is not None else profile.qualified_score_threshold
                    status = "qualified" if score >= threshold else "scored"
                    record = {
                        "status": status, "match_score": score, "skill_fit": skill_fit,
                        "role_alignment_score": assessment.role_alignment_score,
                        "required_skills": _stored_skills(assessment.required_skills),
                        "core_skills": _stored_skills(assessment.core_skills),
                        "preferred_skills": _stored_skills(assessment.preferred_skills),
                        "matching_model": self.config.model, "profile_version": profile.version,
                        "profile_s3_version": profile_version_id,
                    }
                    stored = self._persist(event, record)
                    if status == "qualified":
                        self.sqs.send_message(QueueUrl=self.config.output_queue_url, MessageBody=json.dumps(stored, separators=(",", ":"), ensure_ascii=False, default=_json_value))
                    results[index] = status
                except Exception as error:
                    self._release_lease(event)
                    errors[index] = error
        return results, errors

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

    def _release_lease(self, event: Mapping[str, Any]) -> None:
        try:
            self.table.delete_item(Key={"source": event["source"], "source_job_id": event["source_job_id"]}, ConditionExpression="#status = :processing", ExpressionAttributeNames={"#status": "status"}, ExpressionAttributeValues={":processing": "processing"})
        except Exception:
            logger.exception("Failed releasing matching lease for source job ID %s", event["source_job_id"])

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
        stored = {"source": event["source"], "source_job_id": event["source_job_id"], "job_event": dynamodb_value(stored_event), **record, "processed_at": datetime.now(timezone.utc).isoformat()}
        self.table.put_item(Item=stored)
        return stored


def openai_assessment(api_key: str, model: str, profile: Profile, event: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "model": model, "store": False, "reasoning": {"effort": OPENAI_REASONING_EFFORT},
        "input": [
            {"role": "developer", "content": ASSESSMENT_INSTRUCTIONS},
            {"role": "user", "content": json.dumps({"candidate_summary": profile.candidate_summary, "candidate_skills": profile.candidate_skills, "job": event["job"]}, ensure_ascii=False)},
        ],
        "text": {"format": {"type": "json_schema", "name": "job_assessment", "strict": True, "schema": ASSESSMENT_SCHEMA}},
    }
    request = Request(OPENAI_RESPONSE_ENDPOINT, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as response:  # nosec B310 - fixed OpenAI URL
            if not 200 <= getattr(response, "status", response.getcode()) < 300:
                raise RuntimeError("OpenAI assessment request failed")
            return parse_openai_response(json.loads(response.read().decode()))
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("OpenAI assessment request failed") from error


def process_sqs_batch(event: Any, matcher: Matcher) -> dict[str, list[dict[str, str]]]:
    failures, valid = [], []
    if not isinstance(event, dict) or not isinstance(event.get("Records"), list):
        raise ValueError("SQS event requires Records")
    for record in event["Records"]:
        message_id = record.get("messageId") if isinstance(record, dict) else None
        try:
            if not isinstance(message_id, str) or not isinstance(record.get("body"), str):
                raise ValueError("Invalid SQS record")
            valid.append((message_id, validate_ingestion_event(json.loads(record["body"]))))
        except (TypeError, ValueError, json.JSONDecodeError):
            if message_id:
                failures.append({"itemIdentifier": message_id})
    try:
        results = matcher.process_many([item[1] for item in valid])
        for (message_id, _), result in zip(valid, results):
            if result is None:
                failures.append({"itemIdentifier": message_id})
    except Exception:
        logger.exception("Failed loading matching batch")
        failures.extend({"itemIdentifier": message_id} for message_id, _ in valid)
    return {"batchItemFailures": failures}


def lambda_handler(event: Any, context: Any) -> dict[str, list[dict[str, str]]]:
    del context
    import boto3
    config = Config.from_environment(os.environ)
    matcher = Matcher(config, boto3.client("s3", region_name=config.profile_region), boto3.client("ssm"), boto3.resource("dynamodb").Table(config.table_name), boto3.client("sqs"), openai_assessment)
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


def _stored_skills(skills: tuple[SkillAssessment, ...]) -> list[dict[str, str | None]]:
    return [{"skill": skill.skill, "candidate_skill": skill.candidate_skill, "evidence": skill.evidence} for skill in skills]


def _json_value(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _is_conditional_failure(error: Exception) -> bool:
    return getattr(error, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException"
