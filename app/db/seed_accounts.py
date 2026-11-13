"""Explicit, development-only test accounts; credentials arrive via stdin."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from uuid import NAMESPACE_URL, uuid5

TEST_ACCOUNTS = (
    ("demo", "Asante demo narration", "en", "contributor", "story-demo"),
    ("nomsa", "Nomsa M.", "zu", "contributor", "story-001"),
    ("thabo", "Thabo K.", "en", "contributor", "story-002"),
    ("amina", "Amina S.", "st", "contributor", "story-003"),
    ("reviewer", "Asante test reviewer", "en", "reviewer", None),
)


def fixture_id(kind: str, name: str) -> str:
    return uuid5(NAMESPACE_URL, f"asante:test:{kind}:{name}").hex


async def seed_accounts(passwords: dict[str, str]) -> None:
    # Keep module metadata importable by the lightweight host setup script.
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from asante_api.auth import HASHER, verify_password
    from asante_api.database import database_url
    from asante_api.models import AccountRecord, ContributorRecord, ProjectRecord, ProjectRevision, StoryRecord
    from .seed import STORIES

    if os.environ.get("ASANTE_ENV") != "development":
        raise ValueError("Asante test accounts are restricted to the development environment")
    if set(passwords) != {item[0] for item in TEST_ACCOUNTS} or any(not isinstance(value, str) or len(value) < 16 for value in passwords.values()):
        raise ValueError("Provide all five local test passwords with at least 16 characters")
    story_by_slug = {item["slug"]: item for item in STORIES}
    engine = create_async_engine(database_url())
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            for slug, name, language, role, story_slug in TEST_ACCOUNTS:
                email = f"{slug}@asante.test"
                account = await session.scalar(select(AccountRecord).where(AccountRecord.email == email))
                if account:
                    if not verify_password(account.password_hash, passwords[slug]) or account.role != role:
                        raise ValueError(f"Existing test account {email} does not match the local credential file; no passwords or roles were changed")
                    contributor_id = account.contributor_id
                else:
                    contributor_id = fixture_id("profile", slug)
                    session.add(ContributorRecord(id=contributor_id, profile={"name": name, "email": email, "bio": "Local Asante test profile.", "language": language}, preferences={}))
                    await session.flush()
                    session.add(AccountRecord(id=fixture_id("account", slug), contributor_id=contributor_id, email=email, password_hash=HASHER.hash(passwords[slug]), role=role))
                    await session.flush()
                if story_slug:
                    fixture = story_by_slug[story_slug]
                    # Only the exact known fixture can be linked; never infer real ownership from a name.
                    await session.execute(update(StoryRecord).where(StoryRecord.id == fixture["id"], StoryRecord.slug == story_slug, StoryRecord.contributor_name == name, StoryRecord.contributor_id.is_(None)).values(contributor_id=contributor_id))
                    project_id = fixture_id("project", slug)
                    if not await session.get(ProjectRecord, project_id):
                        content = {"title": "Test draft — " + fixture["title"], "place": {"nomsa": "Soweto Towers", "amina": "Mapungubwe Hill"}.get(slug, "Constitution Hill"), "language": language, "format": fixture["media_format"], "audience": "Community listeners", "transcript": "Editable test draft. Replace this with your own story before submitting.", "claim": "", "source": "", "consent": False, "plan": None, "suggestion": "pending", "uploadId": None}
                        session.add(ProjectRecord(id=project_id, contributor_id=contributor_id, version=1, content=content))
                        await session.flush()
                        session.add(ProjectRevision(id=fixture_id("revision", slug), project_id=project_id, version=1, content=content))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(seed_accounts(json.load(sys.stdin)))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print("Asante test accounts and fixture profile links are ready; existing records and passwords were preserved.")
