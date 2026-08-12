"""
Tests for FastCopy CLI Subprocess Driver (core/fastcopy.py).
"""
import os
import tempfile
import pytest
from core.fastcopy import FastCopyRunner, resolve_fastcopy_executable

def test_resolve_fastcopy_executable_fallback(tmp_path):
    # Pass a non-existent custom path, should return None if nowhere else found
    exe = resolve_fastcopy_executable(custom_path=str(tmp_path / "fake_fastcopy.exe"))
    assert exe is None or os.path.exists(exe)

def test_resolve_fastcopy_executable_custom(tmp_path):
    mock_exe = tmp_path / "FastCopy.exe"
    mock_exe.write_text("mock executable")
    resolved = resolve_fastcopy_executable(custom_path=str(mock_exe))
    assert resolved == str(mock_exe)

def test_fallback_copy_execution(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    f1 = src_dir / "file1.txt"
    f1.write_text("content 1")
    f2 = src_dir / "file2.txt"
    f2.write_text("content 2")

    runner = FastCopyRunner(fastcopy_executable_path=None)  # None forces fallback mode
    lines = list(runner.execute_manifest_copy([str(f1), str(f2)], str(dst_dir)))
    
    assert os.path.exists(dst_dir / "file1.txt")
    assert os.path.exists(dst_dir / "file2.txt")
    assert any("file1.txt" in line for line in lines)
