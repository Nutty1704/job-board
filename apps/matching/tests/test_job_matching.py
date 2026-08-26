import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import job_matching  # noqa: E402


def profile_data(**overrides):
    value = {
        "version": "2026-08-25-llm-v1",
        "candidate_summary": "DevOps, MLOps, platform, and full-stack engineer with AWS experience.",
        "candidate_skills": ["python", "typescript", "react", "aws", "kubernetes"],
        "filters": {
            "allowed_locations": ["sydney", "melbourne"],
            "excluded_phrases": ["security clearance required"],
            "max_required_experience_years": 3,
        },
        "qualified_score_threshold": 65,
    }
    value.update(overrides)
    return value


def event(source_job_id="123", **job_overrides):
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
        "source_job_id": source_job_id,
        "source_url": f"https://example.test/{source_job_id}",
        "ingested_at": "2026-08-20T00:00:00Z",
        "search": {"country": "au", "location": "Sydney", "query": "software engineer", "page": 1},
        "job": job,
        "raw": {"provider": "payload"},
    }


def assessment(role_alignment_score=80, required=None, core=None, preferred=None):
    return {
        "role_alignment_score": role_alignment_score,
        "required_skills": required or [],
        "core_skills": core or [],
        "preferred_skills": preferred or [],
    }


def skill(name, candidate_skill=None, evidence="Required in the job description."):
    return {"skill": name, "candidate_skill": candidate_skill, "evidence": evidence}


class ProfileAndScoringTests(unittest.TestCase):
    def test_dynamodb_value_converts_nested_floats_to_decimals(self):
        value = {"salary": 150000.0, "ranges": [120000.5]}

        self.assertEqual(
            job_matching.dynamodb_value(value),
            {"salary": Decimal("150000.0"), "ranges": [Decimal("120000.5")]},
        )

    def test_profile_requires_curated_candidate_skills(self):
        value = profile_data()
        del value["candidate_skills"]

        with self.assertRaisesRegex(ValueError, "invalid format"):
            job_matching.parse_profile(json.dumps(value).encode())

    def test_hard_filter_keeps_objective_constraints_only(self):
        profile = job_matching.parse_profile(json.dumps(profile_data()).encode())

        self.assertIsNone(job_matching.hard_filter(event(title="Data Scientist", description="R and Python."), profile))
        self.assertEqual(job_matching.hard_filter(event(location={"display_name": "Brisbane"}), profile), "location_not_allowed")
        self.assertEqual(job_matching.hard_filter(event(description="Security clearance required."), profile), "excluded_phrase")
        self.assertEqual(job_matching.hard_filter(event(description="Requires at least 4 years of professional experience."), profile), "experience_requirement_exceeds_limit")

    def test_weighted_score_treats_missing_preferred_skills_as_low_impact(self):
        result = job_matching.parse_assessment(
            assessment(
                role_alignment_score=80,
                required=[skill("Python", "python"), skill("AWS", "aws")],
                core=[skill("React", "react"), skill("TypeScript", "typescript")],
                preferred=[skill("Django")],
            ),
            ("python", "typescript", "react", "aws", "kubernetes"),
        )

        skill_fit, match_score = job_matching.score_assessment(result)

        self.assertEqual(skill_fit, 95)
        self.assertEqual(match_score, 93)

    def test_score_redistributes_empty_skill_group_weight(self):
        result = job_matching.parse_assessment(
            assessment(role_alignment_score=60, required=[skill("Python", "python")], core=[skill("Kubernetes")]),
            ("python",),
        )

        skill_fit, match_score = job_matching.score_assessment(result)

        self.assertEqual(skill_fit, 74)
        self.assertEqual(match_score, 72)

    def test_assessment_rejects_candidate_skill_outside_profile(self):
        with self.assertRaisesRegex(ValueError, "candidate_skill"):
            job_matching.parse_assessment(assessment(required=[skill("Java", "java")]), ("python",))

    def test_response_parser_requires_structured_output(self):
        with self.assertRaisesRegex(ValueError, "structured output"):
            job_matching.parse_openai_response({"output": []})


class FakeDynamo:
    def __init__(self):
        self.items = {}
        self.requests = []
        self.deleted = []

    def put_item(self, **kwargs):
        self.requests.append(kwargs)
        item = kwargs["Item"]
        key = (item["source"], item["source_job_id"])
        if key in self.items and self.items[key].get("status") in {"scored", "qualified", "filtered_out"}:
            raise self.conditional_error()
        self.items[key] = item

    def delete_item(self, **kwargs):
        self.deleted.append(kwargs)
        self.items.pop((kwargs["Key"]["source"], kwargs["Key"]["source_job_id"]), None)

    @staticmethod
    def conditional_error():
        class ConditionalCheckFailedException(Exception):
            response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        return ConditionalCheckFailedException()


class FakeS3:
    def get_object(self, **kwargs):
        return {"Body": type("Body", (), {"read": lambda self: json.dumps(profile_data()).encode()})(), "VersionId": "profile-v1"}


class FakeParameterStore:
    def get_parameter(self, **kwargs):
        return {"Parameter": {"Value": '{"api_key":"key"}'}}


class FakeSqs:
    def __init__(self):
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)


class WorkerTests(unittest.TestCase):
    def matcher(self, dynamo=None, sqs=None, assessor=None):
        return job_matching.Matcher(
            job_matching.Config.from_environment({}), FakeS3(), FakeParameterStore(), dynamo or FakeDynamo(), sqs or FakeSqs(),
            assessor or (lambda *_: assessment(required=[skill("Python", "python")])),
        )

    def test_worker_persists_explainable_luna_score_and_publishes_qualified_job(self):
        dynamo, sqs = FakeDynamo(), FakeSqs()
        matching = self.matcher(
            dynamo,
            sqs,
            lambda *_: assessment(
                role_alignment_score=80,
                required=[skill("Python", "python"), skill("AWS", "aws")],
                core=[skill("React", "react")],
            ),
        )

        self.assertEqual(matching.process(event()), "qualified")
        stored = dynamo.items[("adzuna", "123")]
        self.assertEqual(stored["matching_model"], "gpt-5.6-luna")
        self.assertEqual(stored["skill_fit"], 100)
        self.assertEqual(stored["role_alignment_score"], 80)
        self.assertEqual(stored["match_score"], 97)
        self.assertNotIn("raw", stored["job_event"])
        self.assertNotIn("raw_similarity", stored)
        self.assertEqual(len(sqs.messages), 1)

    def test_worker_serializes_decimal_job_values_when_publishing_qualified_job(self):
        dynamo, sqs = FakeDynamo(), FakeSqs()
        matching = self.matcher(dynamo, sqs)

        self.assertEqual(matching.process(event(latitude=-33.865715)), "qualified")

        published = json.loads(sqs.messages[0]["MessageBody"])
        self.assertEqual(published["job_event"]["job"]["latitude"], -33.865715)

    def test_worker_releases_lease_when_luna_assessment_fails(self):
        dynamo = FakeDynamo()
        matching = self.matcher(dynamo, assessor=lambda *_: (_ for _ in ()).throw(RuntimeError("OpenAI failed")))

        with self.assertRaisesRegex(RuntimeError, "OpenAI failed"):
            matching.process(event())

        self.assertEqual(dynamo.items, {})
        self.assertEqual(len(dynamo.deleted), 1)

    def test_handler_retries_only_luna_failed_message_in_batch(self):
        dynamo = FakeDynamo()
        matching = self.matcher(
            dynamo,
            assessor=lambda _key, _model, _profile, candidate: (_ for _ in ()).throw(RuntimeError("OpenAI failed"))
            if candidate["source_job_id"] == "bad" else assessment(required=[skill("Python", "python")]),
        )
        batch = {"Records": [
            {"messageId": "good", "body": json.dumps(event("good"))},
            {"messageId": "bad", "body": json.dumps(event("bad"))},
        ]}

        self.assertEqual(job_matching.process_sqs_batch(batch, matching), {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        self.assertEqual(dynamo.items[("adzuna", "good")]["status"], "qualified")
        self.assertNotIn(("adzuna", "bad"), dynamo.items)
