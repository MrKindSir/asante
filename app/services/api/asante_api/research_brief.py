"""Contributor questionnaire inputs, separate from generated research and reports."""
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field


class ResearchBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knownMaterial: str = Field(default="", max_length=5000)
    questions: str = Field(default="", max_length=5000)
    context: str = Field(default="", max_length=5000)
    priorities: str = Field(default="", max_length=5000)
    uncertainties: str = Field(default="", max_length=5000)


def research_inputs(content: dict) -> dict:
    return {key: content.get(key) for key in (
        "title", "place", "language", "format", "audience", "claim", "source", "transcript", "researchBrief",
    )}


def research_input_hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(research_inputs(content), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def document_hash(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def brief_complete(content: dict) -> bool:
    brief = content.get("researchBrief") or {}
    return bool((content.get("claim") or "").strip() and (brief.get("questions") or "").strip())
