"""
Tests for Suffix Renamer Helper (utils/suffix_renamer.py).
"""
import os
import pytest
import tempfile
from core.db import DatabaseManager
from utils.suffix_renamer import rename_suffix_in_backup

@pytest.fixture
def mock_backup_environment(tmp_path):
    root_dir = tmp_path / "BACKUP_ROOT"
    root_dir.mkdir()

    sub = root_dir / "2026" / "2026-08" / "2026-08-12"
    sub.mkdir(parents=True)

    f1 = sub / "20260812_150000_AnatKP(C).JPG"
    f1.write_bytes(b"DATA_1")

    f2 = sub / "20260812_150100_AnatKP(C).JPG"
    f2.write_bytes(b"DATA_2")

    db = DatabaseManager(str(root_dir))
    db.register_file("hash1", "IMG_0001.JPG", "DCIM/IMG_0001.JPG", 6, "2026-08-12T15:00:00", "EXIF")
    db.register_file("hash2", "IMG_0002.JPG", "DCIM/IMG_0002.JPG", 6, "2026-08-12T15:01:00", "EXIF")

    db.update_transfer_status("hash1", "E:/DCIM/IMG_0001.JPG", str(f1), "COPIED")
    db.update_transfer_status("hash2", "E:/DCIM/IMG_0002.JPG", str(f2), "COPIED")
    db.checkpoint()

    return str(root_dir), str(f1), str(f2)

def test_rename_suffix_all_files(mock_backup_environment):
    root_dir, f1_old, f2_old = mock_backup_environment

    stats = rename_suffix_in_backup(
        root_dir=root_dir,
        old_suffix="AnatKP(C)",
        new_suffix="IdanPresser(C)"
    )

    assert stats["renamed_count"] == 2
    assert not os.path.exists(f1_old)
    assert not os.path.exists(f2_old)

    new_f1 = f1_old.replace("AnatKP(C)", "IdanPresser(C)")
    new_f2 = f2_old.replace("AnatKP(C)", "IdanPresser(C)")
    assert os.path.exists(new_f1)
    assert os.path.exists(new_f2)

def test_rename_suffix_with_file_list_full_paths(mock_backup_environment, tmp_path):
    root_dir, f1_old, f2_old = mock_backup_environment

    list_file = tmp_path / "file_list.txt"
    list_file.write_text(f"{f1_old}\n")

    stats = rename_suffix_in_backup(
        root_dir=root_dir,
        old_suffix="AnatKP(C)",
        new_suffix="IdanPresser(C)",
        file_list_path=str(list_file)
    )

    assert stats["renamed_count"] == 1
    new_f1 = f1_old.replace("AnatKP(C)", "IdanPresser(C)")
    assert os.path.exists(new_f1)
    assert os.path.exists(f2_old)  # f2 was not in list, remains unchanged

def test_rename_suffix_with_file_list_basenames_only(mock_backup_environment, tmp_path):
    root_dir, f1_old, f2_old = mock_backup_environment

    # Pass ONLY the basename in file_list.txt
    basename1 = os.path.basename(f1_old)
    list_file = tmp_path / "file_list_basenames.txt"
    list_file.write_text(f"{basename1}\n")

    stats = rename_suffix_in_backup(
        root_dir=root_dir,
        old_suffix="AnatKP(C)",
        new_suffix="IdanPresser(C)",
        file_list_path=str(list_file)
    )

    assert stats["renamed_count"] == 1
    new_f1 = f1_old.replace("AnatKP(C)", "IdanPresser(C)")
    assert os.path.exists(new_f1)
    assert not os.path.exists(f1_old)
    assert os.path.exists(f2_old)  # f2 was not in list, remains unchanged
