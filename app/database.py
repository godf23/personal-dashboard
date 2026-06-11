import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.config import BASE_DIR

DB_PATH = BASE_DIR / "data" / "dashboard.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                icon_url TEXT,
                click_count INTEGER NOT NULL DEFAULT 0,
                last_clicked_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weather_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                lat REAL,
                lon REAL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS news_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weather_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                station_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                temp_f REAL,
                humidity_pct REAL,
                rain_mm REAL,
                source_type TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_weather_obs_loc_time
                ON weather_observations(location_id, observed_at);

            CREATE TABLE IF NOT EXISTS weather_predictions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                logged_at TEXT NOT NULL,
                source_name TEXT NOT NULL,
                temp_f REAL,
                humidity_pct REAL,
                rain_chance_pct REAL,
                pressure_hpa REAL,
                wind_mph REAL,
                raw_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_weather_pred_loc_time
                ON weather_predictions_log(location_id, logged_at);

            CREATE TABLE IF NOT EXISTS weather_source_bias (
                location_id INTEGER NOT NULL,
                source_name TEXT NOT NULL,
                variable TEXT NOT NULL,
                bias_value REAL NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                window_start TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (location_id, source_name, variable)
            );

            CREATE TABLE IF NOT EXISTS weather_source_scores (
                location_id INTEGER NOT NULL,
                source_name TEXT NOT NULL,
                mae_temp REAL,
                score REAL NOT NULL DEFAULT 1.0,
                bad_streak INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (location_id, source_name)
            );

            CREATE TABLE IF NOT EXISTS weather_kalman_state (
                location_id INTEGER NOT NULL,
                variable TEXT NOT NULL,
                estimate REAL NOT NULL,
                error_cov REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (location_id, variable)
            );

            CREATE TABLE IF NOT EXISTS news_read (
                url TEXT PRIMARY KEY,
                read_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS saved_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                source TEXT,
                description TEXT,
                image_url TEXT,
                published_at TEXT,
                notes TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                saved_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS news_source_prefs (
                source TEXT PRIMARY KEY,
                weight INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS news_category_prefs (
                category TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS link_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES link_folders(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_link_folders_parent
                ON link_folders(parent_id);
            """
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(links)").fetchall()}
        if "icon_url" not in cols:
            conn.execute("ALTER TABLE links ADD COLUMN icon_url TEXT")
        if "folder_id" not in cols:
            conn.execute("ALTER TABLE links ADD COLUMN folder_id INTEGER REFERENCES link_folders(id)")
        if "description" not in cols:
            conn.execute("ALTER TABLE links ADD COLUMN description TEXT")
        if "sort_order" not in cols:
            conn.execute("ALTER TABLE links ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")

        _seed_news_prefs(conn)


def _seed_news_prefs(conn: sqlite3.Connection) -> None:
    defaults = {
        "news_age_filter": '{"mode": "7d", "days": 7}',
        "news_keyword_blacklist": "[]",
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO preferences (key, value) VALUES (?, ?)",
            (key, value),
        )


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_preference(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_preference(key: str, value: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO preferences (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
