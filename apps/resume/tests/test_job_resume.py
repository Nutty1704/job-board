import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import job_resume  # noqa: E402


def profile_data():
    return {
        "version": "2026-08-25",
        "candidate_summary": "Early-career software engineer.",
        "filters": {"required_skills_any": ["python"], "allowed_locations": ["sydney"], "excluded_phrases": [], "max_required_experience_years": 3},
        "qualified_score_threshold": 80,
        "resume": {
            "identity": {"name": "Ada Example", "contact": "ada@example.test", "headline": "Software Engineer"},
            "summary": "Early-career software engineer.",
            "skill_catalog": {"Languages": ["Go", "Python"], "Cloud": ["AWS", "Kubernetes"]},
            "education": [{"institution": "Example University", "qualification": "Bachelor of Computer Science", "dates": "2020–2023"}],
            "additional_information": ["Australian permanent resident"],
            "experience": [
                {"id": "rokt", "kind": "technical", "employer": "Rokt", "title": "Software Engineer", "dates": "2024–Present", "source_bullets": [
                    {"id": "rokt-go", "text": "Shipped Go services.", "tags": ["go", "platform"]},
                    {"id": "rokt-k8s", "text": "Operated Kubernetes workloads.", "tags": ["kubernetes", "ownership"]},
                    {"id": "rokt-ci", "text": "Built CI pipelines.", "tags": ["ci/cd"]},
                    {"id": "rokt-api", "text": "Built APIs.", "tags": ["backend"]},
                    {"id": "rokt-data", "text": "Improved data reliability.", "tags": ["data"]},
                ]},
                {"id": "retail", "kind": "transferable", "employer": "Shop", "title": "Team Member", "dates": "2020–2023", "source_bullets": [
                    {"id": "retail-team", "text": "Worked with customers.", "tags": ["communication"]},
                    {"id": "retail-own", "text": "Owned shift tasks.", "tags": ["ownership"]},
                ]},
            ],
            "projects": [{"id": "platform", "name": "Experiment Platform", "dates": "2025", "source_bullets": [
                {"id": "platform-fullstack", "text": "Built a full-stack experiment platform.", "tags": ["python", "react"]},
                {"id": "platform-oauth", "text": "Added OAuth SSO.", "tags": ["security"]},
            ]}],
        },
    }


def high_match():
    return {"source": "adzuna", "source_job_id": "123", "profile_s3_version": "profile-v1", "job_event": {"job": {"title": "Platform Engineer", "description": "Go and Kubernetes."}}}


class ProfileValidationTests(unittest.TestCase):
    def test_parse_profile_requires_tagged_resume_source_bullets(self):
        value = profile_data()
        del value["resume"]["experience"][0]["source_bullets"][0]["tags"]

        with self.assertRaisesRegex(ValueError, "tags"):
            job_resume.parse_resume_profile(json.dumps(value).encode())

    def test_parse_profile_rejects_unknown_project_preference(self):
        value = profile_data()
        value["resume"]["projects"][0]["preference"] = "avoid"

        with self.assertRaisesRegex(ValueError, "preference"):
            job_resume.parse_resume_profile(json.dumps(value).encode())

    def test_validate_selection_rejects_unknown_source_reference(self):
        profile = job_resume.parse_resume_profile(json.dumps(profile_data()).encode())
        selection = {"summary": "Early-career software engineer.", "skill_groups": [{"group": "Languages", "skills": ["Go"]}], "experience": [{"id": "rokt", "source_bullet_ids": ["made-up"]}], "projects": []}

        with self.assertRaisesRegex(ValueError, "unknown source bullet"):
            job_resume.validate_selection(selection, profile)

    def test_validate_selection_enforces_role_bullet_counts(self):
        profile = job_resume.parse_resume_profile(json.dumps(profile_data()).encode())
        selection = {"summary": "Early-career software engineer.", "skill_groups": [{"group": "Languages", "skills": ["Go"]}], "experience": [{"id": "rokt", "source_bullet_ids": ["rokt-go", "rokt-k8s", "rokt-ci"]}, {"id": "retail", "source_bullet_ids": ["retail-team"]}], "projects": []}

        with self.assertRaisesRegex(ValueError, "technical experience"):
            job_resume.validate_selection(selection, profile)

    def test_selection_schema_requires_each_experience_with_its_bullet_limits(self):
        profile = job_resume.parse_resume_profile(json.dumps(profile_data()).encode())

        schema = job_resume._selection_schema(profile)
        experience = schema["properties"]["experience"]
        rokt = experience["properties"]["rokt"]
        retail = experience["properties"]["retail"]

        self.assertEqual(experience["required"], ["rokt", "retail"])
        self.assertFalse(experience["additionalProperties"])
        self.assertEqual(rokt["minItems"], 4)
        self.assertEqual(rokt["maxItems"], 5)
        self.assertEqual(rokt["items"]["enum"], ["rokt-go", "rokt-k8s", "rokt-ci", "rokt-api", "rokt-data"])
        self.assertEqual(retail["minItems"], 1)
        self.assertEqual(retail["maxItems"], 2)

    def test_validate_selection_rejects_duplicate_bullet_ids(self):
        profile = job_resume.parse_resume_profile(json.dumps(profile_data()).encode())
        selection = {"summary": "Early-career software engineer.", "skill_groups": [{"group": "Languages", "skills": ["Go"]}], "experience": [{"id": "rokt", "source_bullet_ids": ["rokt-go", "rokt-go", "rokt-go", "rokt-go"]}, {"id": "retail", "source_bullet_ids": ["retail-team"]}], "projects": []}

        with self.assertRaisesRegex(ValueError, "duplicate source bullet"):
            job_resume.validate_selection(selection, profile)


class FakeS3:
    def __init__(self, existing_keys=None):
        self.puts = []
        self.existing_keys = set(existing_keys or [])

    def get_object(self, **kwargs):
        if kwargs["Key"] == "matching/current.json":
            return {"Body": Body(json.dumps(profile_data()).encode()), "VersionId": "profile-v1"}
        return {"Body": Body(b"template"), "VersionId": "template-v2"}

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        self.existing_keys.add(kwargs["Key"])
        return {"VersionId": "artifact-v3"}

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.existing_keys:
            raise FileNotFoundError(kwargs["Key"])
        return {"VersionId": "artifact-v3"}


class Body:
    def __init__(self, value): self.value = value
    def read(self): return self.value


class FakeParameters:
    def get_parameter(self, **kwargs): return {"Parameter": {"Value": '{"api_key":"test-key"}'}}


class ConsumerTests(unittest.TestCase):
    def selection(self):
        return {"summary": "Early-career software engineer.", "skill_groups": [{"group": "Languages", "skills": ["Go"]}], "experience": [{"id": "rokt", "source_bullet_ids": ["rokt-go", "rokt-k8s", "rokt-ci", "rokt-api"]}, {"id": "retail", "source_bullet_ids": ["retail-team"]}], "projects": [{"id": "platform", "source_bullet_ids": ["platform-fullstack"]}]}

    def consumer(self, s3=None, request=None):
        return job_resume.ResumeConsumer(job_resume.Config.from_environment({}), s3 or FakeS3(), FakeParameters(), request or (lambda *_: {"id": "resp-1", "output_text": json.dumps(self.selection())}), lambda template, context: b"docx")

    def test_consumer_stores_rendered_artifact_at_job_scoped_s3_key(self):
        consumer = self.consumer()
        result = consumer.process(high_match())

        self.assertEqual(result, "completed")
        upload = consumer.s3.puts[0]
        self.assertEqual(upload["Key"], "resumes/123.docx")
        self.assertEqual(upload["Metadata"]["profile-s3-version"], "profile-v1")
        self.assertEqual(upload["Metadata"]["source"], "adzuna")
        self.assertEqual(upload["Metadata"]["source-job-id"], "123")
        self.assertEqual(upload["Tagging"], "expires-after-days=21")

    def test_consumer_accepts_profile_keyed_experience_selection(self):
        selection = self.selection()
        selection["experience"] = {
            "rokt": ["rokt-go", "rokt-k8s", "rokt-ci", "rokt-api"],
            "retail": ["retail-team"],
        }
        requests = []
        consumer = self.consumer(request=lambda request: requests.append(request) or {"id": "resp-1", "output_text": json.dumps(selection)})

        self.assertEqual(consumer.process(high_match()), "completed")
        schema = requests[0]["text"]["format"]["schema"]["properties"]["experience"]
        self.assertEqual(schema["required"], ["rokt", "retail"])
        self.assertEqual(schema["properties"]["rokt"]["minItems"], 4)
        self.assertEqual(schema["properties"]["retail"]["maxItems"], 2)

    def test_existing_job_resume_skips_model_call(self):
        calls = []
        consumer = self.consumer(FakeS3({"resumes/123.docx"}), lambda *_: calls.append(True))

        self.assertEqual(consumer.process(high_match()), "duplicate")
        self.assertEqual(calls, [])

    def test_openai_request_uses_strict_responses_json_schema(self):
        captured = []
        job_resume.openai_response("secret", "gpt-5.6-luna", {"job": {}}, lambda request: captured.append(request) or {"id": "r", "output_text": "{}"})

        self.assertEqual(captured[0]["reasoning"]["effort"], "low")
        self.assertTrue(captured[0]["text"]["format"]["strict"])

    def test_batch_retries_only_active_or_failed_work(self):
        response = job_resume.process_sqs_batch({"Records": [{"messageId": "active", "body": json.dumps(high_match())}]}, type("C", (), {"process": lambda self, _: "retry"})())
        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "active"}]})
