"""
Tests for batched ExifTool metadata extraction (core/metadata.py).

The per-file path spawned one exiftool.exe per file (~430ms of process startup each),
which dominated every ingest mode. Batch extraction must produce the same per-file
metadata while collapsing N spawns into one invocation per chunk.
"""
import os
import json
import subprocess

import pytest

from core.metadata import MetadataExtractor


JPEG_STUB = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\x00" * 512
    + b"\xff\xd9"
)


@pytest.fixture
def media_files(tmp_path):
    paths = []
    for i in range(5):
        p = tmp_path / f"IMG_{i:04d}.JPG"
        p.write_bytes(JPEG_STUB)
        paths.append(str(p))
    return paths


def test_batch_returns_a_record_for_every_input_path(media_files):
    results = MetadataExtractor.extract_full_metadata_batch(media_files)

    assert set(results.keys()) == set(media_files)
    for meta in results.values():
        # Same contract as extract_full_metadata: every catalog column present.
        assert "camera_make" in meta
        assert "width" in meta
        assert "raw_json" in meta


def test_batch_spawns_one_exiftool_process_for_the_whole_chunk(media_files, monkeypatch):
    calls = []
    real_run = subprocess.run

    def counting_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", counting_run)

    if MetadataExtractor.resolve_exiftool_path() is None:
        pytest.skip("exiftool not available in this environment")

    MetadataExtractor.extract_full_metadata_batch(media_files, chunk_size=100)

    assert len(calls) == 1, f"expected a single exiftool invocation, got {len(calls)}"


def test_batch_chunks_large_inputs(media_files, monkeypatch):
    if MetadataExtractor.resolve_exiftool_path() is None:
        pytest.skip("exiftool not available in this environment")

    calls = []
    real_run = subprocess.run
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, *a, **k: (calls.append(cmd), real_run(cmd, *a, **k))[1]
    )

    MetadataExtractor.extract_full_metadata_batch(media_files, chunk_size=2)

    # 5 files at chunk_size 2 -> 3 invocations
    assert len(calls) == 3


def test_batch_falls_back_per_file_when_exiftool_missing(media_files, monkeypatch):
    monkeypatch.setattr(MetadataExtractor, "resolve_exiftool_path", classmethod(lambda cls: None))

    results = MetadataExtractor.extract_full_metadata_batch(media_files)

    assert set(results.keys()) == set(media_files)
    for meta in results.values():
        assert "raw_json" in meta


def test_batch_handles_unicode_and_spaced_filenames(tmp_path):
    tricky = []
    for name in ("café shot.JPG", "上海_0001.JPG", "a b c.JPG"):
        p = tmp_path / name
        p.write_bytes(JPEG_STUB)
        tricky.append(str(p))

    results = MetadataExtractor.extract_full_metadata_batch(tricky)

    assert set(results.keys()) == set(tricky)


def test_batch_result_matches_single_file_extraction(media_files):
    """Batching must not change what lands in the catalog."""
    single = MetadataExtractor.extract_full_metadata(media_files[0])
    batched = MetadataExtractor.extract_full_metadata_batch(media_files)[media_files[0]]

    # raw_json ordering/content comes from the same source; compare the mapped columns.
    for key in (
        "camera_make", "camera_model", "lens_model", "iso", "aperture",
        "width", "height", "video_codec", "latitude", "longitude",
    ):
        assert batched[key] == single[key], f"column '{key}' diverged between batch and single"


def test_batch_on_empty_input_returns_empty_dict():
    assert MetadataExtractor.extract_full_metadata_batch([]) == {}


def test_resolve_exiftool_path_is_cached(monkeypatch):
    """Path resolution ran shutil.which() per file; it must resolve once."""
    MetadataExtractor.resolve_exiftool_path.cache_clear()

    import shutil as _shutil
    which_calls = []
    real_which = _shutil.which

    def counting_which(name, *a, **k):
        which_calls.append(name)
        return real_which(name, *a, **k)

    monkeypatch.setattr(_shutil, "which", counting_which)

    MetadataExtractor.resolve_exiftool_path()
    first = len(which_calls)
    for _ in range(10):
        MetadataExtractor.resolve_exiftool_path()

    assert len(which_calls) == first, "resolve_exiftool_path re-ran shutil.which on cached calls"
