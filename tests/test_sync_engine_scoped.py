"""
Tests for sd_backup-a4i: post-import reconciliation must support a SCOPED walk limited
to the destination date-folders touched by a backup batch, instead of re-walking the
entire (potentially multi-TB) archive. Scoped mode only indexes uncataloged files under
the given subdirs.
"""
import os
import pytest
from core.db import DatabaseManager
from core.sync_engine import calculate_sync_diff, execute_sync


def _touch_media(path, content=b"JPEGDATA_UNIQUE"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def test_scoped_diff_only_walks_given_subdirs(tmp_path):
    root = tmp_path / "ARCHIVE"
    root.mkdir()
    # Two date folders; only one is "touched" by the batch.
    touched = root / "2026" / "2026-03" / "2026-03-29"
    other = root / "2025" / "2025-01" / "2025-01-01"
    _touch_media(str(touched / "IMG_0001.JPG"), b"AAAA_1111")
    _touch_media(str(other / "IMG_9999.JPG"), b"BBBB_2222")

    diff = calculate_sync_diff(str(root), scope_subdirs=[os.path.join("2026", "2026-03", "2026-03-29")])

    found = {os.path.basename(u["file_path"]) for u in diff["uncataloged_files"]}
    assert "IMG_0001.JPG" in found
    assert "IMG_9999.JPG" not in found, "scoped diff must not walk untouched date folders"


def test_scoped_execute_sync_indexes_only_scope(tmp_path):
    root = tmp_path / "ARCHIVE2"
    root.mkdir()
    touched_rel = os.path.join("2026", "2026-03", "2026-03-29")
    _touch_media(str(root / touched_rel / "IMG_0001.JPG"), b"CCCC_3333")
    _touch_media(str(root / "2025" / "IMG_9999.JPG"), b"DDDD_4444")

    result = execute_sync(
        str(root),
        remove_missing=False,
        add_uncataloged=True,
        uncataloged_action="ADD_TO_DB",
        scope_subdirs=[touched_rel],
    )
    assert result["added_records"] == 1

    db = DatabaseManager(str(root))
    with db._get_connection() as conn:
        names = {r["original_filename"] for r in conn.execute(
            "SELECT original_filename FROM file_catalog"
        ).fetchall()}
    assert "IMG_0001.JPG" in names
    assert "IMG_9999.JPG" not in names


def test_unscoped_still_walks_everything(tmp_path):
    root = tmp_path / "ARCHIVE3"
    root.mkdir()
    _touch_media(str(root / "2026" / "IMG_0001.JPG"), b"EEEE_5555")
    _touch_media(str(root / "2025" / "IMG_9999.JPG"), b"FFFF_6666")

    diff = calculate_sync_diff(str(root))  # no scope
    found = {os.path.basename(u["file_path"]) for u in diff["uncataloged_files"]}
    assert {"IMG_0001.JPG", "IMG_9999.JPG"} <= found
