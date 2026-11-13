"""Exercise migrations and the async session on an isolated temporary DB."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asante_api.database import database_url
from asante_api.main import app
from asante_api.storage import storage_client
from app.db.seed_media import seed_demo_media
from fastapi.testclient import TestClient


class DatabaseMigrationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalogue_migrations_seeds_and_public_queries_in_isolated_database(self):
        database_name = "asante_test_" + uuid4().hex[:20]
        admin_connection = psycopg.connect(
            host=os.environ.get("ASANTE_POSTGRES_HOST", "postgres"),
            port=int(os.environ.get("ASANTE_POSTGRES_INTERNAL_PORT", "5432")),
            user=os.environ.get("ASANTE_POSTGRES_USER", "asante"),
            password=os.environ.get("ASANTE_POSTGRES_PASSWORD", "asante_local_dev_only"),
            dbname="postgres",
            autocommit=True,
        )
        created = False
        storage = storage_client()
        test_bucket = "asante-test-" + uuid4().hex
        bucket_created = False
        try:
            storage.make_bucket(test_bucket)
            bucket_created = True
            with patch.dict(os.environ, {"ASANTE_MINIO_BUCKET": test_bucket}):
                seed_demo_media()
                seed_demo_media()
            self.assertEqual(len(list(storage.list_objects(test_bucket))), 1)
            with admin_connection.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE "{database_name}"')
                created = True

            database_env = {
                **os.environ,
                "ASANTE_POSTGRES_DB": database_name,
            }
            migration_command = [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "app/db/alembic.ini",
                "upgrade",
                "head",
            ]
            for _ in range(2):
                completed = subprocess.run(
                    migration_command,
                    check=False,
                    capture_output=True,
                    text=True,
                    env=database_env,
                    timeout=60,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

            seed_command = [sys.executable, "-m", "app.db.seed"]
            for _ in range(2):
                seeded = subprocess.run(
                    seed_command,
                    check=False,
                    capture_output=True,
                    text=True,
                    env=database_env,
                    timeout=60,
                )
                self.assertEqual(seeded.returncode, 0, seeded.stdout + seeded.stderr)

            with psycopg.connect(
                host=database_env.get("ASANTE_POSTGRES_HOST", "postgres"),
                port=int(database_env.get("ASANTE_POSTGRES_INTERNAL_PORT", "5432")),
                user=database_env.get("ASANTE_POSTGRES_USER", "asante"),
                password=database_env.get("ASANTE_POSTGRES_PASSWORD", "asante_local_dev_only"),
                dbname=database_name,
                autocommit=True,
            ) as test_connection:
                with test_connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO asante.stories
                            (id, slug, title, contributor_name, landmark_id, language,
                             media_format, status, transcript, is_demo, active, created_at, media_file)
                        SELECT %s, 'integration-draft', 'Not public', 'Test contributor', id,
                               'en', 'audio', 'draft', '', FALSE, TRUE, now(), 'asante-playback-demo.mp3'
                        FROM asante.landmarks WHERE slug = 'constitution-hill'
                        """,
                        (uuid4(),),
                    )

            engine = create_async_engine(database_url(database_name), pool_pre_ping=True)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                async with sessions() as session:
                    schema = await session.scalar(
                        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'asante'")
                    )
                    postgis_version = await session.scalar(text("SELECT postgis_version()"))
                    revision = await session.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                    landmark_count = await session.scalar(text("SELECT count(*) FROM asante.landmarks"))
                    published_story_count = await session.scalar(
                        text("SELECT count(*) FROM asante.stories WHERE status = 'published'")
                    )
                    draft_story_count = await session.scalar(
                        text("SELECT count(*) FROM asante.stories WHERE status = 'draft'")
                    )
                    location_index = await session.scalar(
                        text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'asante' AND indexname = 'idx_landmarks_location'")
                    )
                self.assertEqual(schema, "asante")
                self.assertTrue(postgis_version)
                self.assertEqual(revision, "0016_requeue_review_evidence_v2")
                self.assertEqual(landmark_count, 9)
                self.assertEqual(published_story_count, 9)
                self.assertEqual(draft_story_count, 1)
                self.assertIn("using gist", location_index.lower())
            finally:
                await engine.dispose()

            with psycopg.connect(
                host=database_env.get("ASANTE_POSTGRES_HOST", "postgres"),
                port=int(database_env.get("ASANTE_POSTGRES_INTERNAL_PORT", "5432")),
                user=database_env.get("ASANTE_POSTGRES_USER", "asante"),
                password=database_env.get("ASANTE_POSTGRES_PASSWORD", "asante_local_dev_only"),
                dbname=database_name,
                autocommit=True,
            ) as test_connection:
                with test_connection.cursor() as cursor:
                    dateline_landmark_id = uuid4()
                    cursor.execute(
                        """
                        INSERT INTO asante.landmarks (id, slug, name, region, location, active)
                        VALUES (%s, 'dateline-test', 'Dateline Test', 'Pacific',
                                ST_GeogFromText('SRID=4326;POINT(179 0)'), TRUE)
                        """,
                        (dateline_landmark_id,),
                    )
                    cursor.execute(
                        """
                        INSERT INTO asante.stories
                            (id, slug, title, contributor_name, landmark_id, language,
                             media_format, status, transcript, is_demo, active, created_at)
                        VALUES (%s, 'dateline-story', 'Across the date line', 'Test contributor',
                                %s, 'en', 'audio', 'published', '', FALSE, TRUE, now())
                        """,
                        (uuid4(), dateline_landmark_id),
                    )

            database_env_with_host = {
                **database_env,
                "ASANTE_POSTGRES_DB": database_name,
                "ASANTE_MINIO_BUCKET": test_bucket,
            }
            with patch.dict(os.environ, database_env_with_host, clear=False):
                with TestClient(app) as client:
                    self.assertEqual(client.get("/health/ready").status_code, 200)
                    landmarks = client.get("/v1/landmarks").json()["items"]
                    self.assertEqual(len(landmarks), 10)
                    self.assertIn("district-six", [item["id"] for item in landmarks])
                    self.assertTrue(all(item["distance_m"] is None for item in landmarks))

                    anywhere = client.get("/v1/stories").json()["items"]
                    self.assertNotIn("integration-draft", [item["id"] for item in anywhere])
                    remote = client.get(
                        "/v1/stories",
                        params={"latitude": 51.5, "longitude": -0.12},
                    ).json()["items"]
                    self.assertEqual(len(anywhere), 10)
                    self.assertEqual({item["id"] for item in anywhere}, {item["id"] for item in remote})
                    self.assertTrue(all(item["distance_m"] is None for item in anywhere))
                    self.assertTrue(all(item["distance_m"] > 1_000_000 for item in remote))
                    self.assertEqual(client.get("/v1/stories?latitude=51").status_code, 422)

                    nearby_landmarks = client.get(
                        "/v1/landmarks/nearby",
                        params={"latitude": -26.2041, "longitude": 28.0473, "radius_m": 10_000},
                    ).json()["items"]
                    self.assertGreaterEqual(len(nearby_landmarks), 1)
                    self.assertEqual(
                        [item["distance_m"] for item in nearby_landmarks],
                        sorted(item["distance_m"] for item in nearby_landmarks),
                    )

                    nearby_stories = client.get(
                        "/v1/stories/nearby",
                        params={"latitude": -26.2041, "longitude": 28.0473, "radius_m": 10_000},
                    ).json()["items"]
                    self.assertTrue(all(item["status"] == "published" for item in nearby_stories))
                    self.assertEqual(
                        client.get(
                            "/v1/stories/story-demo/media",
                            headers={"Range": "bytes=0-99"},
                        ).status_code,
                        206,
                    )
                    self.assertEqual(client.get("/v1/stories/story-001/media").status_code, 404)
                    self.assertEqual(client.get("/v1/stories/unknown/media").status_code, 404)
                    self.assertEqual(client.get("/v1/stories/integration-draft/media").status_code, 404)
                    media_url = next(item["media_url"] for item in anywhere if item["id"] == "story-demo").removeprefix("/asante/api")
                    expected = Path("/workspace/media/asante-playback-demo.mp3").read_bytes()
                    full = client.get(media_url)
                    self.assertEqual(full.content, expected)
                    self.assertEqual(full.headers["content-type"], "audio/mpeg")
                    self.assertEqual(client.head(media_url).headers["content-length"], str(len(expected)))
                    for value, content in [("bytes=0-99", expected[:100]), ("bytes=100-", expected[100:]), ("bytes=-50", expected[-50:])]:
                        partial = client.get(media_url, headers={"Range": value})
                        self.assertEqual(partial.status_code, 206)
                        self.assertEqual(partial.content, content)
                    self.assertEqual(client.get(media_url, headers={"Range": "bytes=999999-"}).status_code, 416)
                    with patch.dict(os.environ, {"ASANTE_MINIO_BUCKET": "asante-nonexistent-" + uuid4().hex}):
                        self.assertEqual(client.get(media_url).status_code, 503)
                        self.assertEqual(client.get("/health/ready").status_code, 503)

                    first_page = client.get("/v2/stories", params={"pageSize": 2}).json()
                    self.assertEqual(len(first_page["items"]), 2)
                    self.assertTrue(first_page["nextCursor"])
                    paged_stories = [item for item in first_page["items"]]
                    cursor = first_page["nextCursor"]
                    while cursor:
                        page = client.get(
                            "/v2/stories",
                            params={"pageSize": 2, "cursor": cursor},
                        ).json()
                        paged_stories.extend(page["items"])
                        cursor = page["nextCursor"]
                    self.assertEqual(len(paged_stories), 10)
                    self.assertEqual(len({item["id"] for item in paged_stories}), 10)
                    self.assertIn("contributorName", paged_stories[0])
                    self.assertIn("mediaFormat", paged_stories[0])

                    first_landmark_page = client.get(
                        "/v2/landmarks", params={"pageSize": 2}
                    ).json()
                    paged_landmarks = list(first_landmark_page["items"])
                    cursor = first_landmark_page["nextCursor"]
                    while cursor:
                        page = client.get(
                            "/v2/landmarks",
                            params={"pageSize": 2, "cursor": cursor},
                        ).json()
                        paged_landmarks.extend(page["items"])
                        cursor = page["nextCursor"]
                    self.assertEqual(len(paged_landmarks), 5)
                    self.assertEqual(len({item["id"] for item in paged_landmarks}), 5)

                    self.assertEqual(
                        [item["id"] for item in client.get(
                            "/v2/stories", params={"language": "ZU"}
                        ).json()["items"]],
                        ["story-001"],
                    )
                    self.assertEqual(
                        {item["id"] for item in client.get(
                            "/v2/stories", params={"mediaFormat": "video"}
                        ).json()["items"]},
                        {
                            "story-002",
                            "testdata-ethiopia",
                            "testdata-idi-amin",
                            "testdata-africa-civilizations",
                            "testdata-snake-wedding",
                            "testdata-folktale",
                        },
                    )
                    self.assertEqual(
                        {item["id"] for item in client.get(
                            "/v2/stories", params={"region": "Johannesburg"}
                        ).json()["items"]},
                        {"story-demo", "story-001", "story-002"},
                    )
                    search_results = client.get(
                        "/v2/stories", params={"search": "Constitution Hill"}
                    ).json()["items"]
                    self.assertEqual(
                        {item["id"] for item in search_results}, {"story-demo", "story-002"}
                    )
                    distant_with_distance = client.get(
                        "/v2/stories",
                        params={"latitude": 51.5, "longitude": -0.12, "pageSize": 100},
                    ).json()["items"]
                    self.assertTrue(
                        all(item["distanceM"] > 1_000_000 for item in distant_with_distance)
                    )
                    first_nearby_page = client.get(
                        "/v2/stories/nearby",
                        params={
                            "latitude": -26.2041,
                            "longitude": 28.0473,
                            "radiusM": 20_000,
                            "pageSize": 2,
                        },
                    ).json()
                    nearby_page_items = list(first_nearby_page["items"])
                    nearby_cursor = first_nearby_page["nextCursor"]
                    while nearby_cursor:
                        page = client.get(
                            "/v2/stories/nearby",
                            params={
                                "latitude": -26.2041,
                                "longitude": 28.0473,
                                "radiusM": 20_000,
                                "pageSize": 2,
                                "cursor": nearby_cursor,
                            },
                        ).json()
                        nearby_page_items.extend(page["items"])
                        nearby_cursor = page["nextCursor"]
                    self.assertEqual(len(nearby_page_items), 3)
                    self.assertEqual(
                        len({item["id"] for item in nearby_page_items}), 3
                    )
                    dateline_results = client.get(
                        "/v2/stories", params={"bbox": "170,-10,-170,10"}
                    ).json()["items"]
                    self.assertEqual([item["id"] for item in dateline_results], ["dateline-story"])
                    self.assertEqual(
                        client.get("/v2/stories", params={"latitude": 0}).status_code,
                        422,
                    )
                    self.assertEqual(
                        client.get("/v2/stories", params={"bbox": "bad"}).status_code,
                        422,
                    )
                    self.assertEqual(
                        client.get("/v2/stories", params={"cursor": "not-valid!"}).status_code,
                        422,
                    )
        finally:
            if bucket_created:
                for item in storage.list_objects(test_bucket):
                    storage.remove_object(test_bucket, item.object_name)
                storage.remove_bucket(test_bucket)
            if created:
                with admin_connection.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            admin_connection.close()


if __name__ == "__main__":
    unittest.main()
