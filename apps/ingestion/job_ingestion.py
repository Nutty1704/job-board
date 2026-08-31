"""Adzuna page-one ingestion Lambda.

The Lambda runtime supplies boto3. Everything else deliberately uses the
Python standard library so the deployment ZIP has no third-party dependencies.
"""

import json
import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import islice
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
SQS_MAX_MESSAGE_BYTES = 256 * 1024
ADZUNA_URL_TEMPLATE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


@dataclass(frozen=True)
class Config:
    country: str
    location: str
    locations: tuple[str, ...]
    query: str
    secret_arn: str
    queue_url: str
    results_per_page: int
    page: int = 1


def load_config(environment: Mapping[str, str]) -> Config:
    required = ("ADZUNA_COUNTRY", "ADZUNA_LOCATION", "ADZUNA_SEARCH_QUERY", "ADZUNA_SECRET_ARN", "JOBS_TO_SCORE_QUEUE_URL")
    missing = [key for key in required if not environment.get(key, "").strip()]
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")

    page_size_value = environment.get("ADZUNA_RESULTS_PER_PAGE", "50")
    try:
        results_per_page = int(page_size_value)
    except (TypeError, ValueError) as error:
        raise ValueError("ADZUNA_RESULTS_PER_PAGE must be an integer between 1 and 100") from error
    if not 1 <= results_per_page <= 100:
        raise ValueError("ADZUNA_RESULTS_PER_PAGE must be an integer between 1 and 100")

    locations = tuple(dict.fromkeys(location.strip() for location in environment["ADZUNA_LOCATION"].split(",") if location.strip()))
    if not locations:
        raise ValueError("ADZUNA_LOCATION must contain at least one location")

    return Config(
        country=environment["ADZUNA_COUNTRY"].strip(),
        location=locations[0],
        locations=locations,
        query=environment["ADZUNA_SEARCH_QUERY"].strip(),
        secret_arn=environment["ADZUNA_SECRET_ARN"].strip(),
        queue_url=environment["JOBS_TO_SCORE_QUEUE_URL"].strip(),
        results_per_page=results_per_page,
    )


def load_credentials(secrets_client: Any, secret_arn: str) -> dict[str, str]:
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret_value = response.get("SecretString")
    if not isinstance(secret_value, str):
        raise ValueError("Adzuna secret must contain a SecretString JSON object")
    try:
        credentials = json.loads(secret_value)
    except json.JSONDecodeError as error:
        raise ValueError("Adzuna secret must be valid JSON") from error
    if not isinstance(credentials, dict):
        raise ValueError("Adzuna secret must be a JSON object")
    for key in ("app_id", "app_key"):
        if not isinstance(credentials.get(key), str) or not credentials[key].strip():
            raise ValueError(f"Adzuna secret field {key} must be a non-empty string")
    return {"app_id": credentials["app_id"], "app_key": credentials["app_key"]}


def build_adzuna_url(config: Config, credentials: Mapping[str, str]) -> str:
    query = urlencode({
        "app_id": credentials["app_id"],
        "app_key": credentials["app_key"],
        "what": config.query,
        "where": config.location,
        "results_per_page": config.results_per_page,
    })
    return f"{ADZUNA_URL_TEMPLATE.format(country=config.country, page=config.page)}?{query}"


def fetch_adzuna_results(config: Config, credentials: Mapping[str, str]) -> list[dict[str, Any]]:
    request = Request(build_adzuna_url(config, credentials), headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:  # nosec B310 - URL is fixed to Adzuna's API host
            status = getattr(response, "status", response.getcode())
            if not 200 <= status < 300:
                raise RuntimeError(f"Adzuna returned HTTP {status}")
            payload = json.loads(response.read().decode("utf-8"))
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("Adzuna request failed") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Adzuna response must contain a results array")
    if not all(isinstance(result, dict) for result in payload["results"]):
        raise ValueError("Adzuna results must contain objects")
    return payload["results"]


def normalize_listing(listing: Mapping[str, Any], config: Config, ingested_at: datetime) -> dict[str, Any]:
    source_job_id = listing.get("id")
    if source_job_id is None or str(source_job_id).strip() == "":
        raise ValueError("Adzuna result is missing id")

    event: dict[str, Any] = {
        "schema_version": 1,
        "source": "adzuna",
        "source_job_id": str(source_job_id),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "search": {"country": config.country, "location": config.location, "query": config.query, "page": config.page},
        "job": {},
        "raw": dict(listing),
    }
    _set_if_present(event, "source_url", listing.get("redirect_url"))

    job = event["job"]
    for field in ("title", "description", "contract_type", "contract_time", "created", "latitude", "longitude"):
        target = "source_created_at" if field == "created" else field
        _set_if_present(job, target, listing.get(field))
    for field in ("company", "location", "category"):
        value = listing.get(field)
        if isinstance(value, dict) and value:
            job[field] = value

    salary: dict[str, Any] = {}
    for source, target in (("salary_min", "min"), ("salary_max", "max")):
        _set_if_present(salary, target, listing.get(source))
    predicted = listing.get("salary_is_predicted")
    if predicted is not None:
        salary["is_predicted"] = _as_bool(predicted)
    if salary:
        salary["currency"] = "AUD"
        job["salary"] = salary
    return event


def serialize_event(event: Mapping[str, Any]) -> tuple[str, bool]:
    body = json.dumps(event, separators=(",", ":"), ensure_ascii=False, default=str)
    if len(body.encode("utf-8")) <= SQS_MAX_MESSAGE_BYTES:
        return body, False
    without_raw = dict(event)
    without_raw.pop("raw", None)
    body = json.dumps(without_raw, separators=(",", ":"), ensure_ascii=False, default=str)
    if len(body.encode("utf-8")) > SQS_MAX_MESSAGE_BYTES:
        raise ValueError("Normalized Adzuna event exceeds the SQS 256 KB message limit")
    return body, True


def publish_events(sqs_client: Any, queue_url: str, events: list[Mapping[str, Any]]) -> int:
    published = 0
    for batch in _batches(events, 10):
        entries = []
        for index, event in enumerate(batch):
            body, raw_dropped = serialize_event(event)
            if raw_dropped:
                LOGGER.warning("Dropping raw payload for source_job_id=%s because it exceeds the SQS size limit", event["source_job_id"])
            entries.append({"Id": str(index), "MessageBody": body})
        response = sqs_client.send_message_batch(QueueUrl=queue_url, Entries=entries)
        if response.get("Failed"):
            failed_ids = ",".join(item.get("Id", "unknown") for item in response["Failed"])
            raise RuntimeError(f"SQS batch publish failed for entries: {failed_ids}")
        published += len(entries)
    return published


def run_ingestion(environment: Mapping[str, str], secrets_client: Any, sqs_client: Any) -> dict[str, int]:
    config = load_config(environment)
    credentials = load_credentials(secrets_client, config.secret_arn)
    ingested_at = datetime.now(timezone.utc)
    allocations = allocate_results(config.results_per_page, config.locations)
    results: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for location in config.locations:
        search_config = replace(config, location=location, results_per_page=allocations[location])
        location_results = fetch_adzuna_results(search_config, credentials)
        results.extend(location_results)
        events.extend(normalize_listing(result, search_config, ingested_at) for result in location_results)
    published = publish_events(sqs_client, config.queue_url, events)
    LOGGER.info("Adzuna ingestion completed: fetched=%d published=%d", len(results), published)
    return {"fetched": len(results), "published": published}


def lambda_handler(event: Any, context: Any) -> dict[str, int]:
    del event, context
    import boto3

    return run_ingestion(os.environ, boto3.client("secretsmanager"), boto3.client("sqs"))


def _set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != "":
        target[key] = value


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _batches(items: list[Mapping[str, Any]], size: int):
    iterator = iter(items)
    while batch := list(islice(iterator, size)):
        yield batch


def allocate_results(total: int, locations: tuple[str, ...]) -> dict[str, int]:
    if not locations:
        raise ValueError("At least one location is required")
    if total < len(locations):
        raise ValueError("ADZUNA_RESULTS_PER_PAGE must include at least one result per location")
    if total > len(locations) * 50:
        raise ValueError("ADZUNA_RESULTS_PER_PAGE cannot exceed 50 results per location")

    base, remainder = divmod(total, len(locations))
    return {location: base + (index < remainder) for index, location in enumerate(locations)}
