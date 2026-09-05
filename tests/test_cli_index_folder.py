"""
Unit tests for CLI --index-folder functionality in main.py.
"""
import os
import subprocess
import sys
import tempfile
import shutil
from main import parse_args


def test_parse_args_index_folder():
    args = parse_args(["--index-folder", r"C:\Photos\Trip", "--force-reextract", "--no-recurse"])
    assert args.index_folder == r"C:\Photos\Trip"
    assert args.force_reextract is True
    assert args.no_recurse is True


def test_cli_index_folder_execution():
    """Runs python main.py --index-folder on a temporary media directory."""
    temp_dir = tempfile.mkdtemp(prefix="sd_cli_idx_")
    try:
        f1 = os.path.join(temp_dir, "photo1.jpg")
        with open(f1, "wb") as fh:
            fh.write(b"dummy photo 1 content 123456789")

        cmd = [sys.executable, "main.py", "--index-folder", temp_dir]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        assert res.returncode == 0
        assert "Indexing complete" in res.stdout

        # Verify DB exists
        db_path = os.path.join(temp_dir, ".sd_backup_catalog.db")
        assert os.path.exists(db_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
