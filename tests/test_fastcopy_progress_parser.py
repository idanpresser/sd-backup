"""
Tests for FastCopy stdout progress line parser in core/fastcopy.py
"""
import pytest
from core.fastcopy import parse_fastcopy_stdout_line

def test_parse_bytes_line():
    line = "Transferred : 5,420,100,000 / 15,041,261,487 Bytes (36.0%)"
    parsed = parse_fastcopy_stdout_line(line)
    assert parsed.get("bytes_transferred") == 5420100000
    assert parsed.get("total_bytes") == 15041261487
    assert parsed.get("bytes_pct") == 36.0

def test_parse_speed_line():
    line = "Speed : 485.2 MB/s (00:00:15)"
    parsed = parse_fastcopy_stdout_line(line)
    assert parsed.get("speed_str") == "485.2 MB/s"

def test_parse_files_line():
    line = "Transferred : 12 / 120 Files"
    parsed = parse_fastcopy_stdout_line(line)
    assert parsed.get("files_transferred") == 12
    assert parsed.get("total_files") == 120

def test_parse_current_file_line():
    line = "Copying : C:\\DCIM\\100EOS\\IMG_0001.JPG"
    parsed = parse_fastcopy_stdout_line(line)
    assert "IMG_0001.JPG" in parsed.get("current_file", "")
