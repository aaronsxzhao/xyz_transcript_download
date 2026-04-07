#!/usr/bin/env python3
"""Inspect and clean Supabase Storage buckets used by this app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.supabase_client import get_supabase_admin_client
from screenshot_extractor import cleanup_expired_assets


def iter_bucket_objects(client, bucket: str, limit: int = 100) -> Iterable[dict]:
    """Yield top-level objects from a bucket using paginated list calls."""
    offset = 0
    while True:
        page = client.storage.from_(bucket).list(
            "",
            {
                "limit": limit,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if not page:
            break
        for item in page:
            yield item
        if len(page) < limit:
            break
        offset += len(page)


def object_size(item: dict) -> int:
    """Best-effort object size extraction from Storage list metadata."""
    metadata = item.get("metadata") or {}
    for candidate in (metadata.get("size"), item.get("size"), metadata.get("contentLength")):
        try:
            return int(candidate or 0)
        except (TypeError, ValueError):
            continue
    return 0


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{size:.2f} {unit}"


def report_bucket(client, bucket: str) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    for item in iter_bucket_objects(client, bucket):
        count += 1
        total_bytes += object_size(item)
    print(f"{bucket}: {count} object(s), {format_bytes(total_bytes)}")
    return count, total_bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bucket",
        action="append",
        default=[],
        help="Bucket to include in the report. Can be passed multiple times.",
    )
    parser.add_argument(
        "--empty",
        action="append",
        default=[],
        help="Empty a bucket after confirmation. Can be passed multiple times.",
    )
    parser.add_argument(
        "--delete-bucket",
        action="append",
        default=[],
        help="Delete an already-empty bucket. Can be passed multiple times.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required for destructive actions such as --empty and --delete-bucket.",
    )
    parser.add_argument(
        "--cleanup-expired",
        type=int,
        metavar="DAYS",
        help="Delete generated screenshots/thumbnails older than DAYS from local disk and Supabase.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = get_supabase_admin_client()
    if not client:
        print("Supabase admin client is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.")
        return 1

    buckets = client.storage.list_buckets()
    bucket_ids = [bucket.id for bucket in buckets]
    report_targets = args.bucket or bucket_ids

    print("Supabase storage usage:")
    total_objects = 0
    total_bytes = 0
    for bucket in report_targets:
        if bucket not in bucket_ids:
            print(f"{bucket}: bucket not found")
            continue
        count, bucket_bytes = report_bucket(client, bucket)
        total_objects += count
        total_bytes += bucket_bytes
    print(f"Total: {total_objects} object(s), {format_bytes(total_bytes)}")

    destructive_targets = args.empty or args.delete_bucket or (args.cleanup_expired is not None)
    if destructive_targets and not args.yes:
        print("Refusing destructive action without --yes.")
        return 2

    if args.cleanup_expired is not None:
        stats = cleanup_expired_assets(args.cleanup_expired)
        print(
            "Expired media cleanup: "
            f"local_deleted={stats.get('local_deleted', 0)}, "
            f"remote_deleted={stats.get('remote_deleted', 0)}, "
            f"remote_skipped_unknown_age={stats.get('remote_skipped_unknown_age', 0)}"
        )

    for bucket in args.empty:
        if bucket not in bucket_ids:
            print(f"Skip empty {bucket}: bucket not found")
            continue
        client.storage.empty_bucket(bucket)
        print(f"Emptied bucket: {bucket}")

    if args.delete_bucket:
        remaining_ids = {bucket.id for bucket in client.storage.list_buckets()}
        for bucket in args.delete_bucket:
            if bucket not in remaining_ids:
                print(f"Skip delete {bucket}: bucket not found")
                continue
            client.storage.delete_bucket(bucket)
            print(f"Deleted bucket: {bucket}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
