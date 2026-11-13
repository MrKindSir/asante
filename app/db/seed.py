"""Insert the stable Asante public demonstration catalogue if it is absent."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from geoalchemy2.elements import WKTElement
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import update
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
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-0f7b6e8d6f01"),
        "slug": "addis-ababa",
        "name": "Addis Ababa",
        "region": "Ethiopia",
        "latitude": 9.0320,
        "longitude": 38.7469,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-0f7b6e8d6f02"),
        "slug": "kampala",
        "name": "Kampala",
        "region": "Uganda",
        "latitude": 0.3476,
        "longitude": 32.5825,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-0f7b6e8d6f03"),
        "slug": "cairo",
        "name": "Cairo",
        "region": "Egypt",
        "latitude": 30.0444,
        "longitude": 31.2357,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-0f7b6e8d6f04"),
        "slug": "lagos",
        "name": "Lagos",
        "region": "Nigeria",
        "latitude": 6.5244,
        "longitude": 3.3792,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-0f7b6e8d6f05"),
        "slug": "accra",
        "name": "Accra",
        "region": "Ghana",
        "latitude": 5.6037,
        "longitude": -0.1870,
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
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-1f7b6e8d6f01"),
        "slug": "testdata-ethiopia",
        "title": "Ancient Ground, Living Nation",
        "contributor_name": "Asante TestData · Ethiopia",
        "landmark_slug": "addis-ababa",
        "language": "en",
        "media_format": "video",
        "status": "published",
        "media_file": None,
        "transcript": "Illustrative TestData catalogue record based on the Ethiopia clip. The clip is test media, not a field recording from this map anchor.",
        "is_demo": True,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-1f7b6e8d6f02"),
        "slug": "testdata-idi-amin",
        "title": "Fear Inside the Dictator's House",
        "contributor_name": "Asante TestData · Idi Amin",
        "landmark_slug": "kampala",
        "language": "en",
        "media_format": "video",
        "status": "published",
        "media_file": None,
        "transcript": "Illustrative TestData catalogue record based on the Idi Amin documentary clip. The clip is test media, not a personal testimony.",
        "is_demo": True,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-1f7b6e8d6f03"),
        "slug": "testdata-africa-civilizations",
        "title": "Civilizations Before the Single Story",
        "contributor_name": "Asante TestData · Africa's Great Civilizations",
        "landmark_slug": "cairo",
        "language": "en",
        "media_format": "video",
        "status": "published",
        "media_file": None,
        "transcript": "Illustrative TestData catalogue record based on the Africa's Great Civilizations clip. The clip is educational test media, not an Asante field recording.",
        "is_demo": True,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-1f7b6e8d6f04"),
        "slug": "testdata-snake-wedding",
        "title": "When the Bride Was Other Than Human",
        "contributor_name": "Asante TestData · African Folktale",
        "landmark_slug": "lagos",
        "language": "en",
        "media_format": "video",
        "status": "published",
        "media_file": None,
        "transcript": "Illustrative TestData catalogue record based on an African folktale clip. The clip is story media, not ethnographic proof or a personal account.",
        "is_demo": True,
    },
    {
        "id": UUID("4d5a2a4e-9e70-5e68-9e0f-1f7b6e8d6f05"),
        "slug": "testdata-folktale",
        "title": "Shadows Still Speak in Oduko",
        "contributor_name": "Asante TestData · Folktale",
        "landmark_slug": "accra",
        "language": "en",
        "media_format": "video",
        "status": "published",
        "media_file": None,
        "transcript": "Illustrative TestData catalogue record based on a public folktale clip. Oduko is a story setting; this is not a verified community oral history.",
        "is_demo": True,
    },
)

STALE_NON_AFRICA_LANDMARK_SLUGS = ("london", "mexico-city", "sydney")
STALE_NON_AFRICA_STORY_SLUGS = ("world-listening-room", "world-crossroads", "world-southern-edge")


async def seed_public_catalogue() -> None:
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    landmark_ids = {item["slug"]: item["id"] for item in LANDMARKS}
    try:
        async with sessions.begin() as session:
            await session.execute(
                update(StoryRecord)
                .where(StoryRecord.slug.in_(STALE_NON_AFRICA_STORY_SLUGS))
                .values(active=False, status="archived")
            )
            await session.execute(
                update(LandmarkRecord)
                .where(LandmarkRecord.slug.in_(STALE_NON_AFRICA_LANDMARK_SLUGS))
                .values(active=False)
            )
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
