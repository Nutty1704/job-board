import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import job_matching  # noqa: E402


def profile_data(**overrides):
    value = {
        "version": "2026-08-20",
        "candidate_summary": "Python engineer with AWS experience.",
        "filters": {
            "required_skills_any": ["python", "aws"],
            "allowed_locations": ["sydney", "melbourne"],
            "excluded_phrases": ["security clearance required"],
            "max_required_experience_years": 2,
        },
        "qualified_score_threshold": 80,
    }
    value.update(overrides)
    return value


def event(**job_overrides):
    job = {
        "title": "Software Engineer",
        "description": "Build Python services on AWS.",
        "company": {"display_name": "Acme"},
        "location": {"display_name": "Sydney NSW", "area": ["Sydney", "NSW"]},
    }
    job.update(job_overrides)
    return {
        "schema_version": 1,
        "source": "adzuna",
        "source_job_id": "123",
        "source_url": "https://example.test/123",
        "ingested_at": "2026-08-20T00:00:00Z",
        "search": {"country": "au", "location": "Sydney", "query": "software engineer", "page": 1},
        "job": job,
        "raw": {"provider": "payload"},
    }


class ProfileAndMatchingTests(unittest.TestCase):
    def test_default_profile_key_uses_project_data_prefix(self):
        config = job_matching.Config.from_environment({})

        self.assertEqual(config.profile_key, "matching/current.json")

    def test_parse_profile_reads_hard_filters(self):
        profile = job_matching.parse_profile(json.dumps(profile_data()).encode())

        self.assertEqual(profile.version, "2026-08-20")
        self.assertEqual(profile.required_skills_any, ("python", "aws"))
        self.assertEqual(profile.qualified_score_threshold, 80)

    def test_validate_event_rejects_missing_source_id(self):
        invalid = event()
        del invalid["source_job_id"]

        with self.assertRaisesRegex(ValueError, "source_job_id"):
            job_matching.validate_ingestion_event(invalid)

    def test_hard_filter_accepts_eligible_sydney_python_job(self):
        profile = job_matching.parse_profile(json.dumps(profile_data()).encode())

        self.assertIsNone(job_matching.hard_filter(event(), profile))

    def test_hard_filter_rejects_each_required_reason(self):
        profile = job_matching.parse_profile(json.dumps(profile_data()).encode())
        cases = [
            (event(description=" "), "missing_description"),
            (event(location={"display_name": "Brisbane"}), "location_not_allowed"),
            (event(description="Python role. Security clearance required."), "excluded_phrase"),
            (event(description="Build Java services."), "required_skill_missing"),
            (event(description="Requires at least 3 years of professional experience with Python."), "experience_requirement_exceeds_limit"),
            (event(description="Python role; 3 years of professional experience required."), "experience_requirement_exceeds_limit"),
        ]

        for candidate, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(job_matching.hard_filter(candidate, profile), expected)

    def test_preferred_experience_does_not_filter_job(self):
        profile = job_matching.parse_profile(json.dumps(profile_data()).encode())
        candidate = event(description="Python and AWS. 5 years professional experience preferred.")

        self.assertIsNone(job_matching.hard_filter(candidate, profile))

    def test_job_summary_omits_raw_payload(self):
        summary = job_matching.build_job_summary(event())

        self.assertIn("Title: Software Engineer", summary)
        self.assertNotIn("provider", summary)

    def test_cosine_score_clamps_negative_similarity(self):
        self.assertEqual(job_matching.match_score([1.0, 0.0], [-1.0, 0.0]), (0.0, 0))
        self.assertEqual(job_matching.match_score([3.0, 4.0], [3.0, 4.0]), (1.0, 100))

    def test_embedding_response_requires_vector_per_input(self):
        with self.assertRaisesRegex(ValueError, "one embedding per input"):
            job_matching.parse_embeddings({"data": [{"embedding": [0.1]}]}, 2)


class FakeDynamo:
    def __init__(self):
        self.items = {}

    def put_item(self, **kwargs):
        item = kwargs["Item"]
        key = (item["source"], item["source_job_id"])
        if key in self.items and self.items[key].get("status") in {"scored", "qualified", "filtered_out"}:
            raise self.conditional_error()
        self.items[key] = item

    def update_item(self, **kwargs):
        key = (kwargs["Key"]["source"], kwargs["Key"]["source_job_id"])
        existing = self.items[key]
        existing.update(kwargs["ExpressionAttributeValues"][":record"])

    @staticmethod
    def conditional_error():
        class ConditionalCheckFailedException(Exception):
            response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        return ConditionalCheckFailedException()


class FakeS3:
    def get_object(self, **kwargs):
        return {"Body": type("Body", (), {"read": lambda self: json.dumps(profile_data()).encode()})(), "VersionId": "profile-v1"}


class FakeParameterStore:
    def __init__(self):
        self.requests = []

    def get_parameter(self, **kwargs):
        self.requests.append(kwargs)
        return {"Parameter": {"Value": '{"api_key":"key"}'}}


class FakeSqs:
    def __init__(self):
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)


class FailingSqs:
    def send_message(self, **kwargs):
        raise RuntimeError("queue unavailable")


class WorkerTests(unittest.TestCase):
    def test_worker_loads_openai_key_from_secure_parameter(self):
        parameter_store = FakeParameterStore()
        matching = job_matching.Matcher(job_matching.Config.from_environment({}), FakeS3(), parameter_store, FakeDynamo(), FakeSqs(), lambda *_: None)

        self.assertEqual(matching._api_key(), "key")
        self.assertEqual(parameter_store.requests, [{"Name": "openai", "WithDecryption": True}])

    def test_worker_drops_filtered_job_without_embedding_output_or_storage(self):
        dynamo, sqs = FakeDynamo(), FakeSqs()
        matching = job_matching.Matcher(job_matching.Config.from_environment({}), FakeS3(), FakeParameterStore(), dynamo, sqs, lambda *_: None)

        result = matching.process(event(description="Java only"))

        self.assertEqual(result, "filtered_out")
        self.assertEqual(dynamo.items, {})
        self.assertEqual(sqs.messages, [])

    def test_worker_qualifies_and_publishes_without_raw_event_data(self):
        dynamo, sqs = FakeDynamo(), FakeSqs()
        http = lambda *_: {"data": [{"embedding": [1.0, 0.0]}, {"embedding": [1.0, 0.0]}]}
        matching = job_matching.Matcher(job_matching.Config.from_environment({}), FakeS3(), FakeParameterStore(), dynamo, sqs, http)

        result = matching.process(event())

        self.assertEqual(result, "qualified")
        stored = dynamo.items[("adzuna", "123")]
        self.assertEqual(stored["match_score"], 100)
        self.assertNotIn("raw", stored["job_event"])
        self.assertEqual(len(sqs.messages), 1)
        self.assertNotIn("raw", json.loads(sqs.messages[0]["MessageBody"])["job_event"])

    def test_completed_duplicate_skips_embedding(self):
        dynamo, sqs = FakeDynamo(), FakeSqs()
        calls = []
        matching = job_matching.Matcher(job_matching.Config.from_environment({}), FakeS3(), FakeParameterStore(), dynamo, sqs, lambda *_: calls.append(True))
        dynamo.items[("adzuna", "123")] = {"source": "adzuna", "source_job_id": "123", "status": "scored"}

        self.assertEqual(matching.process(event()), "duplicate")
        self.assertEqual(calls, [])

    def test_handler_returns_invalid_messages_for_partial_batch_retry(self):
        response = job_matching.process_sqs_batch(
            {"Records": [{"messageId": "good", "body": json.dumps(event())}, {"messageId": "bad", "body": "{"}]},
            job_matching.Matcher(job_matching.Config.from_environment({}), FakeS3(), FakeParameterStore(), FakeDynamo(), FakeSqs(), lambda *_: {"data": [{"embedding": [1]}, {"embedding": [1]}]}),
        )

        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "bad"}]})

    def test_handler_retries_message_when_high_match_publish_fails(self):
        with self.assertLogs(job_matching.logger, level="ERROR") as logs:
            response = job_matching.process_sqs_batch(
                {"Records": [{"messageId": "qualified", "body": json.dumps(event())}]},
                job_matching.Matcher(job_matching.Config.from_environment({}), FakeS3(), FakeParameterStore(), FakeDynamo(), FailingSqs(), lambda *_: {"data": [{"embedding": [1]}, {"embedding": [1]}]}),
            )

        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "qualified"}]})
        self.assertIn("qualified", logs.output[0])
        self.assertIn("RuntimeError: queue unavailable", logs.output[0])
        self.assertNotIn("Build Python services on AWS", logs.output[0])
