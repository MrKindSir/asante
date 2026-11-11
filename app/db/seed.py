"""Insert the stable Asante public demonstration catalogue if it is absent."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from geoalchemy2.elements import WKTElement
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asante_api.database import database_url
from asante_api.models import LandmarkRecord, StoryRecord


LANDMARKS = (
    {
        "id": UUID("90d6a1f1-bc01-5d71-9a57-1cb65a58c2a1"),
        "slug": "constitution-hill",
        "name": "Constitution Hill",
        "region": "Johannesburg",
        "latitude": -26.1883,
        "longitude": 28.0368,
    },
    {
        "id": UUID("584b3051-bd9d-565e-a110-d11bb22ad31b"),
        "slug": "soweto-towers",
        "name": "Soweto Towers",
        "region": "Johannesburg",
        "latitude": -26.2344,
        "longitude": 27.9091,
    },
    {
        "id": UUID("0fa9e987-6436-50df-954e-114c0b43dd0c"),
        "slug": "mapungubwe-hill",
        "name": "Mapungubwe Hill",
        "region": "Limpopo",
        "latitude": -22.1920,
        "longitude": 29.4311,
    },
    {
        "id": UUID("728fa1b2-0d71-5f9f-a1cf-f1df0a5a8211"),
        "slug": "district-six",
        "name": "District Six",
        "region": "Cape Town",
        "latitude": -33.9273,
        "longitude": 18.4242,
    },
)

STORIES = (
    {
        "id": UUID("f25cd042-e9e5-531c-8c54-9f11c315bb20"),
        "slug": "story-demo",
        "title": "A place to begin — audio demo",
        "contributor_name": "Asante demo narration",
        "landmark_slug": "constitution-hill",
        "language": "en",
        "media_format": "audio",
        "status": "published",
        "media_file": "asante-playback-demo.mp3",
        "transcript": "Welcome to Asante. Every story begins somewhere. This sample recording is linked to Constitution Hill in Johannesburg. You can listen from anywhere in the world. Choose a landmark to see where its story belongs, then press play when you are ready. Your own location is optional. This is an original synthetic demo narration for testing playback, not a verified heritage account.",
        "is_demo": True,
    },
    {
        "id": UUID("c0724fba-89f4-5978-85b7-625d4bda65f4"),
        "slug": "story-001",
        "title": "The river remembers",
        "contributor_name": "Nomsa M.",
        "landmark_slug": "soweto-towers",
        "language": "zu",
        "media_format": "audio",
        "status": "published",
        "media_file": None,
        "transcript": "",
        "is_demo": False,
    },
    {
        "id": UUID("173e2343-7936-58bc-b8bd-460dc112d24b"),
        "slug": "story-002",
        "title": "A market at first light",
        "contributor_name": "Thabo K.",
        "landmark_slug": "constitution-hill",
        "language": "en",
        "media_format": "video",
        "status": "published",
        "media_file": None,
        "transcript": "",
        "is_demo": False,
    },
    {
        "id": UUID("d2676e42-a13a-5987-82be-d7279cc00d73"),
        "slug": "story-003",
        "title": "The road home",
        "contributor_name": "Amina S.",
        "landmark_slug": "mapungubwe-hill",
        "language": "st",
        "media_format": "audio",
        "status": "published",
        "media_file": None,
        "transcript": "",
        "is_demo": False,
    },
)


async def seed_public_catalogue() -> None:
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    landmark_ids = {item["slug"]: item["id"] for item in LANDMARKS}
    try:
        async with sessions.begin() as session:
            for landmark in LANDMARKS:
                values = {
                    key: value
                    for key, value in landmark.items()
                    if key not in {"latitude", "longitude"}
                }
                values["location"] = WKTElement(
                    f"POINT({landmark['longitude']} {landmark['latitude']})", srid=4326
                )
                statement = insert(LandmarkRecord).values(**values).on_conflict_do_nothing(
                    index_elements=[LandmarkRecord.slug]
                )
                await session.execute(statement)

            for story in STORIES:
                values = {
                    key: value
                    for key, value in story.items()
                    if key != "landmark_slug"
                }
                values["landmark_id"] = landmark_ids[story["landmark_slug"]]
                values["created_at"] = datetime(2026, 11, 7, tzinfo=timezone.utc)
                statement = insert(StoryRecord).values(**values).on_conflict_do_nothing(
                    index_elements=[StoryRecord.slug]
                )
                await session.execute(statement)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_public_catalogue())
