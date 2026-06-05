import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image

from app.services import photos


def sample_image_bytes():
    buffer = BytesIO()
    Image.new("RGB", (64, 32), "red").save(buffer, "JPEG")
    return buffer.getvalue()


@contextmanager
def patched_photo_settings(temp_dir, transport):
    original_client = httpx.Client

    def client_factory(**kwargs):
        return original_client(transport=transport, **kwargs)

    with patch.object(photos.settings, "immich_url", "https://immich.test/api"), patch.object(
        photos.settings, "immich_api_key", "test-key"
    ), patch.object(photos.settings, "immich_timeout", 1), patch.object(
        photos.settings, "photo_cache_dir", Path(temp_dir) / "thumbs"
    ), patch.object(
        photos.settings, "photo_db_path", Path(temp_dir) / "photos.sqlite"
    ), patch.object(
        photos.settings, "photo_thumbnail_width", 40
    ), patch.object(
        photos.settings, "photo_thumbnail_height", 30
    ), patch.object(
        photos.settings, "photo_thumbnail_quality", 80
    ), patch.object(
        photos.settings, "photo_years_back", 1
    ), patch.object(
        photos.settings, "photo_preload_batch", 4
    ), patch.object(
        photos.httpx, "Client", side_effect=client_factory
    ):
        yield


class ImmichPhotoParsingTests(unittest.TestCase):
    def test_extract_assets_handles_supported_immich_shapes(self):
        shapes = [
            {"assets": {"items": [{"id": "nested"}]}},
            {"items": [{"id": "items"}]},
            {"assets": [{"id": "assets-list"}]},
            [{"id": "root-list"}],
        ]

        ids = [photos._extract_assets(shape)[0]["id"] for shape in shapes]

        self.assertEqual(ids, ["nested", "items", "assets-list", "root-list"])

    def test_matching_people_uses_case_insensitive_exact_names(self):
        people = [
            {"id": "roberto", "name": " Roberto "},
            {"id": "roberto-b", "name": "Roberto B"},
        ]

        matches = photos.matching_people(people, ["roberto", "Rob"])

        self.assertEqual([person["id"] for person in matches], ["roberto"])


class ImmichPhotoPayloadTests(unittest.TestCase):
    def test_normal_payload_keeps_requested_year_window(self):
        with patch.object(photos.settings, "photo_years_back", 1):
            payload = photos.normal_search_payload("2026-06-05")

        self.assertEqual(payload["type"], "IMAGE")
        self.assertEqual(payload["takenAfter"], "2025-01-01T00:00:00.000Z")
        self.assertEqual(payload["takenBefore"], "2026-12-31T23:59:59.999Z")
        self.assertNotIn("personIds", payload)

    def test_birthday_payload_has_person_ids_without_date_filters(self):
        payload = photos.birthday_search_payload(["person-1"])

        self.assertEqual(payload, {"type": "IMAGE", "personIds": ["person-1"]})
        self.assertNotIn("takenAfter", payload)
        self.assertNotIn("takenBefore", payload)


class ImmichPhotoCacheTests(unittest.TestCase):
    def test_init_db_replaces_mount_drive_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "photos.sqlite"
            connection = sqlite3.connect(str(db_path))
            try:
                connection.execute(
                    """
                    CREATE TABLE photos (
                        id TEXT PRIMARY KEY,
                        path TEXT NOT NULL UNIQUE,
                        year INTEGER NOT NULL,
                        size INTEGER NOT NULL,
                        mtime REAL NOT NULL,
                        thumb_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            with patch.object(photos.settings, "photo_db_path", db_path):
                photos.init_db()
                connection = sqlite3.connect(str(db_path))
                try:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(photos)").fetchall()}
                finally:
                    connection.close()

        self.assertIn("asset_id", columns)
        self.assertNotIn("path", columns)

    def test_birthday_photo_generates_thumbnail_from_immich_original(self):
        requests = []

        def handler(request):
            if request.url.path == "/api/people":
                return httpx.Response(200, json={"people": [{"id": "person-1", "name": "Roberto"}]})
            if request.url.path == "/api/search/metadata":
                body = json.loads(request.content.decode("utf-8"))
                requests.append(body)
                return httpx.Response(
                    200,
                    json={"assets": {"items": [{"id": "birthday-asset", "originalFileName": "birthday.jpg"}]}},
                )
            if request.url.path == "/api/assets/birthday-asset/original":
                return httpx.Response(200, content=sample_image_bytes())
            return httpx.Response(404)

        with tempfile.TemporaryDirectory() as temp_dir:
            transport = httpx.MockTransport(handler)
            with patched_photo_settings(temp_dir, transport):
                ready = photos.random_ready_photos("2026-06-05", limit=2, birthday_names=["Roberto"])
                thumbnail = photos.thumbnail_for_id(ready[0]["id"])
                thumbnail_exists = thumbnail.exists()

                with Image.open(thumbnail) as image:
                    size = image.size

        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["fileName"], "birthday.jpg")
        self.assertEqual(requests[0]["personIds"], ["person-1"])
        self.assertNotIn("takenAfter", requests[0])
        self.assertTrue(thumbnail_exists)
        self.assertLessEqual(size[0], 40)
        self.assertLessEqual(size[1], 30)

    def test_birthday_without_assets_falls_back_to_normal_random_photo(self):
        requests = []

        def handler(request):
            if request.url.path == "/api/people":
                return httpx.Response(200, json={"people": [{"id": "person-1", "name": "Roberto"}]})
            if request.url.path == "/api/search/metadata":
                body = json.loads(request.content.decode("utf-8"))
                requests.append(body)
                if body.get("personIds"):
                    return httpx.Response(200, json={"assets": {"items": []}})
                return httpx.Response(
                    200,
                    json={"assets": {"items": [{"id": "normal-asset", "originalFileName": "normal.jpg"}]}},
                )
            if request.url.path == "/api/assets/normal-asset/original":
                return httpx.Response(200, content=sample_image_bytes())
            return httpx.Response(404)

        with tempfile.TemporaryDirectory() as temp_dir:
            transport = httpx.MockTransport(handler)
            with patched_photo_settings(temp_dir, transport):
                ready = photos.random_ready_photos("2026-06-05", limit=2, birthday_names=["Roberto"])

        self.assertEqual([photo["fileName"] for photo in ready], ["normal.jpg"])
        self.assertEqual(requests[0]["personIds"], ["person-1"])
        self.assertNotIn("takenAfter", requests[0])
        self.assertEqual(requests[1]["type"], "IMAGE")
        self.assertEqual(requests[1]["takenAfter"], "2025-01-01T00:00:00.000Z")
        self.assertEqual(requests[1]["takenBefore"], "2026-12-31T23:59:59.999Z")


if __name__ == "__main__":
    unittest.main()
