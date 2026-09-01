from meshive.api import diagnostics


def test_storage_diagnostics_is_root_level_and_reports_capacity(tmp_path) -> None:
    result = diagnostics._storage_status(tmp_path)

    assert result["readable"] is True
    assert result["total_bytes"] > 0
    assert result["free_bytes"] >= 0


def test_storage_diagnostics_isolated_when_a_component_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics.shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(OSError("unavailable")),
    )

    result = diagnostics._storage_status(tmp_path)

    assert result == {
        "configured": True,
        "path": tmp_path.as_posix(),
        "readable": False,
        "writable": False,
        "error": "Storage is unavailable",
    }
