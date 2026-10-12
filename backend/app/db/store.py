"""Document store.

Analyses, cached daily temperatures, and geocoder results are JSON documents.
MongoDB is used when `MONGO_URI` connects. Otherwise the same operations run
against TinyDB, a file-backed document database, so the app still stores and
reads JSON documents with no extra service. The collection and key layout is
the same for both.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class DocumentStore(Protocol):
    kind: str

    def get_document(self, collection: str, key: str) -> dict | None: ...

    def put_document(self, collection: str, key: str, document: dict) -> None: ...

    def clear(self) -> None: ...


class TinyStore:
    """TinyDB document store. One JSON file, one table per collection."""

    kind = "tinydb"

    def __init__(self, path: Path) -> None:
        from tinydb import TinyDB

        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(path)
        self._lock = threading.Lock()
        self.path = path

    def get_document(self, collection: str, key: str) -> dict | None:
        from tinydb import Query

        with self._lock:
            found = self._db.table(collection).get(Query()._id == key)
        if not found:
            return None
        return dict(found)

    def put_document(self, collection: str, key: str, document: dict) -> None:
        from tinydb import Query

        payload = {**document, "_id": key}
        with self._lock:
            self._db.table(collection).upsert(payload, Query()._id == key)

    def clear(self) -> None:
        with self._lock:
            self._db.drop_tables()


class MongoStore:
    kind = "mongodb"

    def __init__(self, uri: str, database: str) -> None:
        from pymongo import MongoClient

        self._client = MongoClient(uri, serverSelectionTimeoutMS=600)
        self._client.admin.command("ping")
        self._db = self._client[database]

    def get_document(self, collection: str, key: str) -> dict | None:
        found = self._db[collection].find_one({"_id": key})
        if not found:
            return None
        return dict(found)

    def put_document(self, collection: str, key: str, document: dict) -> None:
        self._db[collection].replace_one({"_id": key}, {**document, "_id": key}, upsert=True)

    def clear(self) -> None:
        for name in ("weather", "analyses", "geocode"):
            self._db[name].delete_many({})


_store: DocumentStore | None = None
_store_lock = threading.Lock()


def create_store(settings: Settings | None = None) -> DocumentStore:
    settings = settings or get_settings()
    preference = settings.store_preference.lower().strip()
    if preference not in {"auto", "mongo", "mongodb", "tinydb"}:
        raise RuntimeError("STORE_PREFERENCE must be auto, mongo, or tinydb")
    if preference in {"auto", "mongo", "mongodb"} and settings.mongo_uri:
        try:
            store: DocumentStore = MongoStore(settings.mongo_uri, settings.mongo_db)
            logger.info("Using MongoDB database %s", settings.mongo_db)
            return store
        except Exception as exc:
            if preference in {"mongo", "mongodb"}:
                raise RuntimeError("MongoDB was requested but could not be reached") from exc
            logger.warning("MongoDB is not reachable (%s). Using the TinyDB document store.", exc.__class__.__name__)
    path = Path(settings.data_dir) / "documents.json"
    logger.info("Using TinyDB document store at %s", path)
    try:
        return TinyStore(path)
    except OSError as exc:
        # Read-only filesystems (serverless hosts) only allow writes under /tmp.
        fallback = Path(tempfile.gettempdir()) / "climate-hazard" / "documents.json"
        logger.warning("Cannot write to %s (%s). Using %s instead.", path, exc.__class__.__name__, fallback)
        return TinyStore(fallback)


def get_store() -> DocumentStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = create_store()
    return _store


def reset_store() -> None:
    """Drop the cached store. Tests use this after pointing DATA_DIR elsewhere."""
    global _store
    with _store_lock:
        _store = None
