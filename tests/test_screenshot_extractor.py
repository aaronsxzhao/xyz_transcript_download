"""Tests for screenshot storage helpers."""

from datetime import datetime, timedelta, timezone

from screenshot_extractor import delete_task_assets
from screenshot_extractor import cleanup_expired_assets


def test_delete_task_assets_removes_matching_local_files(tmp_path, monkeypatch):
    screenshots_dir = tmp_path / "screenshots"
    thumbnails_dir = tmp_path / "thumbnails"
    screenshots_dir.mkdir()
    thumbnails_dir.mkdir()

    monkeypatch.setattr("screenshot_extractor.SCREENSHOTS_DIR", screenshots_dir)
    monkeypatch.setattr("screenshot_extractor.THUMBNAILS_DIR", thumbnails_dir)
    monkeypatch.setattr("screenshot_extractor._get_supabase_storage_client", lambda: None)

    matching_screenshot = screenshots_dir / "task123_00-30.jpg"
    other_screenshot = screenshots_dir / "task999_00-30.jpg"
    matching_thumbnail = thumbnails_dir / "task123.jpg"
    matching_cover = thumbnails_dir / "task123_cover.jpg"

    for path in (matching_screenshot, other_screenshot, matching_thumbnail, matching_cover):
        path.write_bytes(b"test")

    result = delete_task_assets("task123")

    assert result["local_deleted"] == 3
    assert result["remote_deleted"] == 0
    assert not matching_screenshot.exists()
    assert not matching_thumbnail.exists()
    assert not matching_cover.exists()
    assert other_screenshot.exists()


def test_delete_task_assets_handles_missing_files(tmp_path, monkeypatch):
    screenshots_dir = tmp_path / "screenshots"
    thumbnails_dir = tmp_path / "thumbnails"
    screenshots_dir.mkdir()
    thumbnails_dir.mkdir()

    monkeypatch.setattr("screenshot_extractor.SCREENSHOTS_DIR", screenshots_dir)
    monkeypatch.setattr("screenshot_extractor.THUMBNAILS_DIR", thumbnails_dir)
    monkeypatch.setattr("screenshot_extractor._get_supabase_storage_client", lambda: None)

    result = delete_task_assets("missing-task")

    assert result == {
        "task_id": "missing-task",
        "local_deleted": 0,
        "remote_deleted": 0,
    }


def test_cleanup_expired_assets_removes_only_old_local_files(tmp_path, monkeypatch):
    screenshots_dir = tmp_path / "screenshots"
    thumbnails_dir = tmp_path / "thumbnails"
    screenshots_dir.mkdir()
    thumbnails_dir.mkdir()

    monkeypatch.setattr("screenshot_extractor.SCREENSHOTS_DIR", screenshots_dir)
    monkeypatch.setattr("screenshot_extractor.THUMBNAILS_DIR", thumbnails_dir)
    monkeypatch.setattr("screenshot_extractor._get_supabase_storage_client", lambda: None)

    old_file = screenshots_dir / "old.jpg"
    new_file = thumbnails_dir / "new.jpg"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")

    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=30)).timestamp()
    new_ts = (now - timedelta(days=2)).timestamp()

    import os
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))

    result = cleanup_expired_assets(21, now=now)

    assert result["local_deleted"] == 1
    assert result["remote_deleted"] == 0
    assert not old_file.exists()
    assert new_file.exists()
