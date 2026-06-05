import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import photos


class PhotoDatabaseTests(unittest.TestCase):
    def test_init_db_recreates_cache_table_when_year_column_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "photos.sqlite"
            connection = sqlite3.connect(str(db_path))
            try:
                connection.execute(
                    """
                    CREATE TABLE photos (
                        id TEXT PRIMARY KEY,
                        asset_id TEXT NOT NULL UNIQUE,
                        file_name TEXT NOT NULL,
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
                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(photos)").fetchall()
                }
            finally:
                connection.close()

        self.assertIn("year", columns)
        self.assertIn("path", columns)
        self.assertIn("idx_photos_year_status", indexes)


if __name__ == "__main__":
    unittest.main()
