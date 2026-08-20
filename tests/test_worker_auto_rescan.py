"""
Tests for sd_backup-a4i (worker wiring): when auto_rescan is enabled, BackupWorker runs
a post-import reconcile after the transfer, scoped by default to the date-folders it just
touched (never a blind full-drive walk), and does not purge missing records.
"""
import os
import pytest
from PySide6.QtCore import QCoreApplication
from PIL import Image
from core.worker import BackupWorker


def _make_sd_with_one_photo(tmp_path):
    sd = tmp_path / "SD"
    d = sd / "DCIM" / "100EOS"
    d.mkdir(parents=True)
    img = Image.new("RGB", (48, 32), "blue")
    img.save(str(d / "IMG_0001.JPG"), format="JPEG")
    target = tmp_path / "TARGET"
    target.mkdir()
    return sd, target


def test_auto_rescan_calls_scoped_reconcile(tmp_path, monkeypatch):
    sd, target = _make_sd_with_one_photo(tmp_path)
    QCoreApplication.instance() or QCoreApplication([])

    captured = {}

    def fake_execute_sync(root, **kw):
        captured["root"] = root
        captured["scope"] = kw.get("scope_subdirs")
        captured["remove_missing"] = kw.get("remove_missing")
        return {"removed_records": 0, "added_records": 0, "deleted_disk_files": 0, "errors": 0}

    monkeypatch.setattr("core.worker.execute_sync", fake_execute_sync)

    worker = BackupWorker(
        source_card_path=str(sd),
        target_dir=str(target),
        fastcopy_path="",
        custom_suffix="",
        folder_opts={"dcim": True, "private": True, "full_volume": False},
        auto_rescan=True,
    )
    worker.run()

    assert captured, "auto_rescan must trigger a reconcile"
    assert captured["remove_missing"] is False, "post-import reconcile must not purge records"
    assert captured["scope"] is not None, "default reconcile must be scoped, not full-drive"
    assert len(captured["scope"]) >= 1, "at least the touched date folder must be in scope"


def test_no_rescan_when_disabled(tmp_path, monkeypatch):
    sd, target = _make_sd_with_one_photo(tmp_path)
    QCoreApplication.instance() or QCoreApplication([])

    called = {"n": 0}
    monkeypatch.setattr("core.worker.execute_sync", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    worker = BackupWorker(
        source_card_path=str(sd),
        target_dir=str(target),
        fastcopy_path="",
        custom_suffix="",
        folder_opts={"dcim": True, "private": True, "full_volume": False},
        auto_rescan=False,
    )
    worker.run()
    assert called["n"] == 0


def test_full_drive_rescan_passes_no_scope(tmp_path, monkeypatch):
    sd, target = _make_sd_with_one_photo(tmp_path)
    QCoreApplication.instance() or QCoreApplication([])

    captured = {}
    monkeypatch.setattr(
        "core.worker.execute_sync",
        lambda root, **kw: captured.update(scope=kw.get("scope_subdirs"))
        or {"removed_records": 0, "added_records": 0, "deleted_disk_files": 0, "errors": 0},
    )

    worker = BackupWorker(
        source_card_path=str(sd),
        target_dir=str(target),
        fastcopy_path="",
        custom_suffix="",
        folder_opts={"dcim": True, "private": True, "full_volume": False},
        auto_rescan=True,
        rescan_full_drive=True,
    )
    worker.run()
    assert "scope" in captured and captured["scope"] is None, "full-drive rescan passes no scope"
