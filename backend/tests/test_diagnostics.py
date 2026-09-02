from meshive.api import diagnostics


def test_storage_diagnostics_is_root_level_and_reports_capacity(tmp_path) -> None:
    before = set(tmp_path.iterdir())
    result = diagnostics._storage_status(tmp_path)

    assert result["readable"] is True
    assert result["writable"] is True
    assert result["total_bytes"] > 0
    assert result["free_bytes"] >= 0
    assert set(tmp_path.iterdir()) == before


def test_storage_diagnostics_preserves_access_when_capacity_check_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics.shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(OSError("unavailable")),
    )

    result = diagnostics._storage_status(tmp_path)

    assert result["readable"] is True
    assert result["writable"] is True
    assert result["error"] == "Storage capacity is unavailable"


def test_storage_diagnostics_reports_read_only_when_write_probe_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics.tempfile,
        "TemporaryFile",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("read-only")),
    )

    result = diagnostics._storage_status(tmp_path)

    assert result["readable"] is True
    assert result["writable"] is False


def test_storage_diagnostics_rejects_missing_and_non_directory_paths(tmp_path) -> None:
    assert diagnostics._storage_status(tmp_path / "missing")["readable"] is False
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("test")
    assert diagnostics._storage_status(file_path)["writable"] is False
