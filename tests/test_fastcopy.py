"""
Tests for FastCopy CLI Subprocess Driver (core/fastcopy.py).
"""
import os
import tempfile
import pytest
from core.fastcopy import FastCopyRunner, resolve_fastcopy_executable

def test_resolve_fastcopy_executable_fallback(tmp_path):
    exe = resolve_fastcopy_executable(custom_path=str(tmp_path / "fake_fastcopy.exe"))
    assert exe is None or os.path.exists(exe)

def test_resolve_fastcopy_executable_custom_fcp(tmp_path):
    mock_fcp = tmp_path / "fcp.exe"
    mock_fcp.write_text("mock executable")
    resolved = resolve_fastcopy_executable(custom_path=str(mock_fcp))
    assert resolved == str(mock_fcp)

def test_resolve_fastcopy_bin_fcp(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fcp = bin_dir / "fcp.exe"
    fcp.write_text("mock fcp binary")
    
    monkeypatch.chdir(tmp_path)
    resolved = resolve_fastcopy_executable()
    assert resolved == str(fcp)

def test_fallback_copy_execution(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    f1 = src_dir / "file1.txt"
    f1.write_text("content 1")
    f2 = src_dir / "file2.txt"
    f2.write_text("content 2")

    runner = FastCopyRunner(fastcopy_executable_path=None, force_fallback=True)
    lines = list(runner.execute_manifest_copy([str(f1), str(f2)], str(dst_dir)))
    
    assert os.path.exists(dst_dir / "file1.txt")
    assert os.path.exists(dst_dir / "file2.txt")
    assert any("file1.txt" in line for line in lines)
