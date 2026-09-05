"""
Unit tests for FolderIndexer (in-place media folder indexing).
"""
import os
import shutil
import tempfile
import pytest
from core.indexer import FolderIndexer
from core.db import DatabaseManager
from utils.path_formatter import normalize_win_path


@pytest.fixture
def temp_media_folder():
    """Creates a temporary folder structure with dummy images and videos."""
    temp_dir = tempfile.mkdtemp(prefix="sd_test_indexer_")
    
    # Create subfolders
    sub1 = os.path.join(temp_dir, "2026", "08")
    sub2 = os.path.join(temp_dir, "raw_shoots")
    os.makedirs(sub1, exist_ok=True)
    os.makedirs(sub2, exist_ok=True)

    # Create dummy files with distinct contents/sizes
    f1 = os.path.join(temp_dir, "root_photo.jpg")
    f2 = os.path.join(sub1, "nested_photo.jpg")
    f3 = os.path.join(sub2, "shoot_01.arw")
    f4 = os.path.join(sub2, "video_clip.mp4")
    f_non_media = os.path.join(temp_dir, "document.txt")

    for i, f in enumerate((f1, f2, f3, f4, f_non_media), start=1):
        with open(f, "wb") as fh:
            fh.write(b"dummy media content header data " + (b"X" * (i * 20)))

    yield temp_dir

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_discover_media_files(temp_media_folder):
    """Tests discovery of media files and exclusion of non-media files."""
    files = FolderIndexer.discover_media_files(temp_media_folder, include_subdirs=True)
    assert len(files) == 4
    basenames = [os.path.basename(f) for f in files]
    assert "root_photo.jpg" in basenames
    assert "nested_photo.jpg" in basenames
    assert "shoot_01.arw" in basenames
    assert "video_clip.mp4" in basenames
    assert "document.txt" not in basenames

    # Test without subdirectories
    root_only = FolderIndexer.discover_media_files(temp_media_folder, include_subdirs=False)
    assert len(root_only) == 1
    assert os.path.basename(root_only[0]) == "root_photo.jpg"


def test_index_folder_creates_valid_catalog(temp_media_folder):
    """Tests that indexing populates file_catalog, transfer_manifest, file_metadata, and catalog_meta."""
    progress_updates = []
    
    def on_progress(p):
        progress_updates.append(p)

    res = FolderIndexer.index_folder(
        temp_media_folder,
        progress_callback=on_progress,
        include_subdirs=True
    )

    assert res["total_discovered"] == 4
    assert res["added_records"] == 4
    assert res["skipped_records"] == 0
    assert res["errors"] == 0
    assert res["cancelled"] is False

    # Check progress callbacks fired
    assert len(progress_updates) > 0

    # Verify DB contents
    db = DatabaseManager(temp_media_folder)
    with db._get_connection() as conn:
        cursor = conn.cursor()
        
        # Verify file_catalog
        cursor.execute("SELECT * FROM file_catalog")
        catalog_rows = cursor.fetchall()
        assert len(catalog_rows) == 4

        for row in catalog_rows:
            # target_relative_path must be safe archive-relative
            target_rel = row["target_relative_path"]
            assert target_rel is not None
            assert not target_rel.startswith(("/", "\\"))
            assert ":" not in target_rel
            assert ".." not in target_rel
            assert os.path.exists(os.path.join(temp_media_folder, target_rel))

        # Verify transfer_manifest
        cursor.execute("SELECT * FROM transfer_manifest WHERE copy_status = 'COPIED'")
        manifest_rows = cursor.fetchall()
        assert len(manifest_rows) == 4

        # Verify catalog_meta
        assert db.get_generation() >= 1
        assert not db.is_in_progress()


def test_index_folder_incremental(temp_media_folder):
    """Tests incremental indexing where second run skips existing records."""
    res1 = FolderIndexer.index_folder(temp_media_folder, include_subdirs=True)
    assert res1["added_records"] == 4

    # Run again without changes
    res2 = FolderIndexer.index_folder(temp_media_folder, include_subdirs=True)
    assert res2["added_records"] == 0
    assert res2["skipped_records"] == 4

    # Add a new file
    new_file = os.path.join(temp_media_folder, "new_photo.jpg")
    with open(new_file, "wb") as fh:
        fh.write(b"new image data content")

    res3 = FolderIndexer.index_folder(temp_media_folder, include_subdirs=True)
    assert res3["added_records"] == 1
    assert res3["skipped_records"] == 4


def test_index_folder_cancellation(temp_media_folder):
    """Tests cancellation mid-indexing."""
    cancel_flag = {"cancel": False}

    def on_progress(p):
        if p.get("current", 0) >= 1:
            cancel_flag["cancel"] = True

    res = FolderIndexer.index_folder(
        temp_media_folder,
        progress_callback=on_progress,
        is_cancelled=lambda: cancel_flag["cancel"],
        include_subdirs=True
    )

    assert res["cancelled"] is True
    db = DatabaseManager(temp_media_folder)
    assert not db.is_in_progress()
