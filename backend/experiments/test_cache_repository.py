from __future__ import annotations

import pprint
import sys
from pathlib import Path

# Manual experiment script for validating the live Supabase cache repository.
# This should not be imported by app code or automated tests.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from repositories.cache_repository import (  # noqa: E402
    delete_recognition_record_by_id,
    find_recognition_records_by_phash,
    get_recognition_record_by_id,
    save_recognition_record,
)


def main() -> None:
    inserted_record: dict[str, object] | None = None

    try:
        inserted_record = save_recognition_record(
            phash="8f31c4a29e18d9a0",
            clip_embedding=None,
            item_label="Calculator",
            recognition_source="manual_test",
            confidence=1.0,
            verified=True,
            metadata={"test": True},
        )
        print("Inserted record:")
        pprint.pprint(inserted_record)

        record_id = str(inserted_record["id"])

        fetched_record = get_recognition_record_by_id(record_id)
        print("\nFetched by ID:")
        pprint.pprint(fetched_record)

        phash_matches = find_recognition_records_by_phash("8f31c4a29e18d9a0")
        print("\nExact pHash matches:")
        pprint.pprint(phash_matches)
    finally:
        if inserted_record and inserted_record.get("id"):
            deleted_record = delete_recognition_record_by_id(str(inserted_record["id"]))
            print("\nDeleted record:")
            pprint.pprint(deleted_record)


if __name__ == "__main__":
    main()
