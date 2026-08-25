"""Static configuration for the job-matching Lambda."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


DEFAULT_MATCHING_MODEL = "gpt-5.6-luna"
MAX_ASSESSMENT_WORKERS = 5
OPENAI_RESPONSE_ENDPOINT = "https://api.openai.com/v1/responses"
OPENAI_REASONING_EFFORT = "low"
OPENAI_REQUEST_TIMEOUT_SECONDS = 45

ASSESSMENT_INSTRUCTIONS = (
    "Assess this job for the candidate. Extract only skills supported by the job text. "
    "Classify each as required, core, or preferred. candidate_skill must be an exact item from the candidate skills list or null. "
    "Score role alignment from 0 to 100 for the candidate's stated target and experience."
)

EXPERIENCE_PATTERN = re.compile(
    r"(?i)(?:requires?|required|minimum|at least)\s*(?:of\s*)?(\d+)\+?\s+years?(?:\s+of)?\s+professional\s+experience"
)
TRAILING_EXPERIENCE_PATTERN = re.compile(
    r"(?i)(\d+)\+?\s+years?(?:\s+of)?\s+professional\s+experience[^.]{0,80}\b(?:required|minimum|at least)\b"
)
SKILL_GROUP_WEIGHTS = {"required_skills": 0.70, "core_skills": 0.25, "preferred_skills": 0.05}
ASSESSMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["role_alignment_score", "required_skills", "core_skills", "preferred_skills"],
    "properties": {
        "role_alignment_score": {"type": "integer", "minimum": 0, "maximum": 100},
        **{
            group: {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["skill", "candidate_skill", "evidence"],
                    "properties": {
                        "skill": {"type": "string"},
                        "candidate_skill": {"type": ["string", "null"]},
                        "evidence": {"type": "string"},
                    },
                },
            }
            for group in SKILL_GROUP_WEIGHTS
        },
    },
}


@dataclass(frozen=True)
class Config:
    table_name: str
    profile_bucket: str
    profile_key: str
    profile_region: str
    openai_parameter_name: str
    output_queue_url: str
    model: str = DEFAULT_MATCHING_MODEL
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
            model=environment.get("OPENAI_MATCHING_MODEL", DEFAULT_MATCHING_MODEL).strip(),
            lease_seconds=lease_seconds, threshold_override=int(threshold) if threshold else None,
        )
