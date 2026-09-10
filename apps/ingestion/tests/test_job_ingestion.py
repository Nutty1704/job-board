import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import job_ingestion  # noqa: E402


def valid_config():
    return {
        "ADZUNA_COUNTRY": "au",
        "ADZUNA_LOCATION": "Sydney",
        "ADZUNA_SEARCH_QUERY": "software engineer",
        "ADZUNA_SECRET_ARN": "arn:aws:secretsmanager:ap-southeast-2:123:secret:adzuna",
        "JOBS_TO_SCORE_QUEUE_URL": "https://sqs.ap-southeast-2.amazonaws.com/123/jobs",
        "ADZUNA_RESULTS_PER_PAGE": "50",
    }


def valid_listing(**overrides):
    listing = {
        "id": "123456",
        "redirect_url": "https://www.adzuna.com/details/123456",
        "title": "Software Engineer",
        "description": "Build useful things.",
        "company": {"display_name": "Acme"},
        "location": {"display_name": "Sydney NSW", "area": ["Sydney", "NSW"]},
        "category": {"tag": "it-jobs", "label": "IT Jobs"},
        "contract_type": "permanent",
        "contract_time": "full_time",
        "salary_min": 100000,
        "salary_max": 130000,
        "salary_is_predicted": "0",
        "created": "2026-08-17T12:00:00Z",
        "latitude": -33.8688,
        "longitude": 151.2093,
    }
    listing.update(overrides)
    return listing


def fixture_listing():
    fixture_path = Path(__file__).parent / "fixtures" / "adzuna_response.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))["results"][0]


class PackagingTests(unittest.TestCase):
    def test_package_ingestion_does_not_require_zip_executable(self):
        repository_root = Path(__file__).resolve().parents[3]
        just = shutil.which("just")
        mkdir = shutil.which("mkdir")
        shell = shutil.which("sh")
        self.assertIsNotNone(just)
        self.assertIsNotNone(mkdir)
        self.assertIsNotNone(shell)

        with tempfile.TemporaryDirectory() as temporary_directory:
            command_directory = Path(temporary_directory)
            (command_directory / "python3").symlink_to(Path(sys.executable))
            (command_directory / "mkdir").symlink_to(Path(mkdir))
            (command_directory / "sh").symlink_to(Path(shell))
            environment = os.environ | {"PATH": str(command_directory)}

            result = subprocess.run(
                [just, "package-ingestion"],
                cwd=repository_root,
                env=environment,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(repository_root / "dist" / "ingestion.zip") as archive:
            self.assertEqual(archive.namelist(), ["job_ingestion.py"])


class ConfigAndRequestTests(unittest.TestCase):
    def test_load_config_parses_multiple_locations_and_daily_target(self):
        environment = valid_config()
        environment["ADZUNA_LOCATION"] = "Sydney, Melbourne"
        environment["ADZUNA_RESULTS_PER_PAGE"] = "75"

        config = job_ingestion.load_config(environment)

        self.assertEqual(config.locations, ("Sydney", "Melbourne"))
        self.assertEqual(config.results_per_page, 75)

    def test_load_config_removes_duplicate_locations(self):
        environment = valid_config()
        environment["ADZUNA_LOCATION"] = "Sydney, Melbourne, Sydney"

        config = job_ingestion.load_config(environment)

        self.assertEqual(config.locations, ("Sydney", "Melbourne"))

    def test_allocate_results_splits_daily_target_across_locations(self):
        self.assertEqual(job_ingestion.allocate_results(75, ("Sydney", "Melbourne")), {"Sydney": 38, "Melbourne": 37})

    def test_allocate_results_rejects_targets_that_cannot_be_served_per_location(self):
        with self.assertRaisesRegex(ValueError, "50 results per location"):
            job_ingestion.allocate_results(75, ("Sydney",))

        with self.assertRaisesRegex(ValueError, "one result per location"):
            job_ingestion.allocate_results(1, ("Sydney", "Melbourne"))

    def test_load_config_defaults_page_size(self):
        environment = valid_config()
        del environment["ADZUNA_RESULTS_PER_PAGE"]

        config = job_ingestion.load_config(environment)

        self.assertEqual(config.results_per_page, 50)
        self.assertEqual(config.page, 1)

    def test_load_config_rejects_invalid_page_size(self):
        environment = valid_config()
        environment["ADZUNA_RESULTS_PER_PAGE"] = "0"

        with self.assertRaisesRegex(ValueError, "ADZUNA_RESULTS_PER_PAGE"):
            job_ingestion.load_config(environment)

    def test_load_credentials_rejects_malformed_secret(self):
        class Secrets:
            def get_secret_value(self, **kwargs):
                return {"SecretString": '{"app_id": "only-id"}'}

        with self.assertRaisesRegex(ValueError, "app_key"):
            job_ingestion.load_credentials(Secrets(), "secret-arn")

    def test_build_request_uses_page_one_and_configured_search(self):
        config = job_ingestion.load_config(valid_config())

        url = job_ingestion.build_adzuna_url(config, {"app_id": "id value", "app_key": "key/value"})

        self.assertIn("/au/search/1?", url)
        self.assertIn("what=software+engineer", url)
        self.assertIn("where=Sydney", url)
        self.assertIn("results_per_page=50", url)
        self.assertIn("app_id=id+value", url)
        self.assertIn("app_key=key%2Fvalue", url)


class NormalizationTests(unittest.TestCase):
    def test_normalize_listing_emits_versioned_event_with_raw_payload(self):
        config = job_ingestion.load_config(valid_config())
        ingested_at = datetime(2026, 8, 18, tzinfo=timezone.utc)

        event = job_ingestion.normalize_listing(fixture_listing(), config, ingested_at)

        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["source"], "adzuna")
        self.assertEqual(event["source_job_id"], "123456")
        self.assertEqual(event["ingested_at"], "2026-08-18T00:00:00Z")
        self.assertEqual(event["search"], {"country": "au", "location": "Sydney", "query": "software engineer", "page": 1})
        self.assertEqual(event["job"]["salary"], {"min": 100000, "max": 130000, "is_predicted": False, "currency": "AUD"})
        self.assertEqual(event["raw"]["id"], "123456")

    def test_normalize_listing_omits_unavailable_optional_fields(self):
        config = job_ingestion.load_config(valid_config())
        event = job_ingestion.normalize_listing(valid_listing(title=None, company={}, location={}, category={}, salary_min=None, salary_max=None, salary_is_predicted=None, redirect_url=None), config, datetime.now(timezone.utc))

        self.assertNotIn("source_url", event)
        self.assertNotIn("title", event["job"])
        self.assertNotIn("company", event["job"])
        self.assertNotIn("location", event["job"])
        self.assertNotIn("category", event["job"])
        self.assertNotIn("salary", event["job"])

    def test_normalize_listing_requires_source_identifier(self):
        config = job_ingestion.load_config(valid_config())

        with self.assertRaisesRegex(ValueError, "id"):
            job_ingestion.normalize_listing(valid_listing(id=None), config, datetime.now(timezone.utc))

    def test_serialize_event_drops_raw_when_full_message_exceeds_sqs_limit(self):
        event = {"source_job_id": "123", "job": {"title": "ok"}, "raw": {"description": "x" * 270000}}

        body, raw_dropped = job_ingestion.serialize_event(event)

        self.assertTrue(raw_dropped)
        self.assertNotIn("raw", json.loads(body))
        self.assertLessEqual(len(body.encode("utf-8")), job_ingestion.SQS_MAX_MESSAGE_BYTES)


class HandlerTests(unittest.TestCase):
    def test_handler_fetches_and_publishes_daily_target_across_locations(self):
        class Secrets:
            def get_secret_value(self, **kwargs):
                return {"SecretString": json.dumps({"app_id": "id", "app_key": "key"})}

        class Sqs:
            def __init__(self):
                self.calls = []

            def send_message_batch(self, **kwargs):
                self.calls.append(kwargs)
                return {"Successful": kwargs["Entries"]}

        environment = valid_config()
        environment["ADZUNA_LOCATION"] = "Sydney, Melbourne"
        environment["ADZUNA_RESULTS_PER_PAGE"] = "75"
        sqs = Sqs()
        sydney_results = [valid_listing(id=f"sydney-{number}") for number in range(38)]
        melbourne_results = [valid_listing(id=f"melbourne-{number}") for number in range(37)]

        with patch.object(job_ingestion, "fetch_adzuna_results", side_effect=[sydney_results, melbourne_results]) as fetch:
            result = job_ingestion.run_ingestion(environment, Secrets(), sqs)

        self.assertEqual(result, {"fetched": 75, "published": 75})
        self.assertEqual([(call.args[0].location, call.args[0].results_per_page) for call in fetch.call_args_list], [("Sydney", 38), ("Melbourne", 37)])
        events = [json.loads(entry["MessageBody"]) for call in sqs.calls for entry in call["Entries"]]
        self.assertEqual({event["search"]["location"] for event in events}, {"Sydney", "Melbourne"})

    def test_handler_fetches_and_publishes_all_results_in_batches_of_ten(self):
        class Secrets:
            def get_secret_value(self, **kwargs):
                return {"SecretString": json.dumps({"app_id": "id", "app_key": "key"})}

        class Sqs:
            def __init__(self):
                self.calls = []

            def send_message_batch(self, **kwargs):
                self.calls.append(kwargs)
                return {"Successful": kwargs["Entries"]}

        sqs = Sqs()
        results = [valid_listing(id=str(number)) for number in range(11)]
        with patch.object(job_ingestion, "fetch_adzuna_results", return_value=results):
            result = job_ingestion.run_ingestion(valid_config(), Secrets(), sqs)

        self.assertEqual(result, {"fetched": 11, "published": 11})
        self.assertEqual([len(call["Entries"]) for call in sqs.calls], [10, 1])
        first_event = json.loads(sqs.calls[0]["Entries"][0]["MessageBody"])
        self.assertEqual(first_event["source_job_id"], "0")

    def test_handler_fails_for_adzuna_api_error(self):
        class Secrets:
            def get_secret_value(self, **kwargs):
                return {"SecretString": json.dumps({"app_id": "id", "app_key": "key"})}

        with patch.object(job_ingestion, "fetch_adzuna_results", side_effect=RuntimeError("Adzuna returned HTTP 500")):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                job_ingestion.run_ingestion(valid_config(), Secrets(), object())

    def test_handler_fails_when_sqs_reports_failed_entry(self):
        class Secrets:
            def get_secret_value(self, **kwargs):
                return {"SecretString": json.dumps({"app_id": "id", "app_key": "key"})}

        class Sqs:
            def send_message_batch(self, **kwargs):
                return {"Successful": [], "Failed": [{"Id": "0", "Code": "InternalError"}]}

        with patch.object(job_ingestion, "fetch_adzuna_results", return_value=[valid_listing()]):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                job_ingestion.run_ingestion(valid_config(), Secrets(), Sqs())

    def test_handler_fails_for_malformed_source_result(self):
        class Secrets:
            def get_secret_value(self, **kwargs):
                return {"SecretString": json.dumps({"app_id": "id", "app_key": "key"})}

        with patch.object(job_ingestion, "fetch_adzuna_results", return_value=[valid_listing(id=None)]):
            with self.assertRaisesRegex(ValueError, "id"):
                job_ingestion.run_ingestion(valid_config(), Secrets(), object())

    def test_handler_returns_zero_counts_for_empty_search(self):
        class Secrets:
            def get_secret_value(self, **kwargs):
                return {"SecretString": json.dumps({"app_id": "id", "app_key": "key"})}

        with patch.object(job_ingestion, "fetch_adzuna_results", return_value=[]):
            self.assertEqual(job_ingestion.run_ingestion(valid_config(), Secrets(), object()), {"fetched": 0, "published": 0})


if __name__ == "__main__":
    unittest.main()
