"""
Tests for compute_hash_from_values in MetadataExtractor (core/metadata.py).
"""
import pytest
from datetime import datetime
from core.metadata import MetadataExtractor

def test_compute_hash_from_values():
    dt = datetime(2026, 8, 12, 15, 30, 45)
    size = 1048576
    
    h1 = MetadataExtractor.compute_hash_from_values(dt, size)
    assert isinstance(h1, str)
    assert len(h1) == 64  # SHA256 hex digest length
    
    # Verify deterministic output
    h2 = MetadataExtractor.compute_hash_from_values(dt, size)
    assert h1 == h2
