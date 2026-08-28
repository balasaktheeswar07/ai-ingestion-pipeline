import sqlite3
from pathlib import Path


class IdempotencyStore:
    """SQLite local implementation; its key contract maps directly to Redis/Postgres later."""
    def __init__(self, path: Path = Path("data/processed/frontier_atlas.db")) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS processed (fingerprint TEXT PRIMARY KEY, record_type TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        self.connection.commit()

    def claim(self, fingerprint: str, record_type: str) -> bool:
        try:
            self.connection.execute("INSERT INTO processed (fingerprint, record_type) VALUES (?, ?)", (fingerprint, record_type))
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def close(self) -> None:
        self.connection.close()
