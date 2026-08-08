import os
import sys

import pytest

from meshive.archives.sevenzip_cli import (
    ArchiveReadError,
    _run_bounded_command,
    _run_bounded_extraction,
    extract_archive_entry,
    parse_technical_listing,
)


def test_parses_7zip_technical_listing() -> None:
    output = """Path = meshes
Size = 0
Packed Size = 0
Modified = 2025-01-01 12:00:00
Attributes = D
Folder = +

Path = meshes/model.stl
Size = 12345
Packed Size = 4567
Modified = 2025-01-01 12:00:01
Attributes = A
CRC = ABCDEF12
Folder = -

"""

    entries = parse_technical_listing(output)

    assert len(entries) == 2
    assert entries[0].path == "meshes"
    assert entries[0].is_directory is True
    assert entries[1].name == "model.stl"
    assert entries[1].size_bytes == 12345
    assert entries[1].compressed_size_bytes == 4567
    assert entries[1].crc == "ABCDEF12"


def test_archive_command_output_is_bounded_while_process_runs() -> None:
    with pytest.raises(ArchiveReadError, match="output exceeds"):
        _run_bounded_command(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 2048)"],
            environment=dict(os.environ),
            timeout_seconds=10,
            max_output_bytes=1024,
            command_name=sys.executable,
        )


def test_archive_command_is_stopped_after_timeout() -> None:
    with pytest.raises(ArchiveReadError, match="exceeded"):
        _run_bounded_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            environment=dict(os.environ),
            timeout_seconds=0.05,
            max_output_bytes=1024,
            command_name=sys.executable,
        )


def test_extracts_binary_output_to_a_bounded_file(tmp_path) -> None:
    destination = tmp_path / "entry.bin"

    written = _run_bounded_extraction(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(bytes(range(256)) * 4)",
        ],
        destination_path=destination,
        environment=dict(os.environ),
        timeout_seconds=10,
        max_output_bytes=2048,
        command_name=sys.executable,
    )

    assert written == 1024
    assert destination.read_bytes() == bytes(range(256)) * 4


def test_bounded_extraction_removes_partial_output_when_limit_is_exceeded(
    tmp_path,
) -> None:
    destination = tmp_path / "entry.bin"

    with pytest.raises(ArchiveReadError, match="exceeds"):
        _run_bounded_extraction(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 4096)",
            ],
            destination_path=destination,
            environment=dict(os.environ),
            timeout_seconds=10,
            max_output_bytes=1024,
            command_name=sys.executable,
        )

    assert not destination.exists()


def test_bounded_extraction_stops_after_timeout(tmp_path) -> None:
    destination = tmp_path / "entry.bin"

    with pytest.raises(ArchiveReadError, match="extraction exceeded"):
        _run_bounded_extraction(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            destination_path=destination,
            environment=dict(os.environ),
            timeout_seconds=0.05,
            max_output_bytes=1024,
            command_name=sys.executable,
        )

    assert not destination.exists()


def test_bounded_extraction_reports_stderr_and_removes_failed_output(tmp_path) -> None:
    destination = tmp_path / "entry.bin"

    with pytest.raises(ArchiveReadError, match="broken archive"):
        _run_bounded_extraction(
            [
                sys.executable,
                "-c",
                (
                    "import sys; sys.stdout.buffer.write(b'partial'); "
                    "sys.stderr.write('broken archive'); sys.exit(2)"
                ),
            ],
            destination_path=destination,
            environment=dict(os.environ),
            timeout_seconds=10,
            max_output_bytes=1024,
            command_name=sys.executable,
        )

    assert not destination.exists()


@pytest.mark.parametrize("entry_path", ["@entries.txt", "*.jpg", "image?.png", "a\n.jpg"])
def test_rejects_unsafe_archive_entry_selection(entry_path: str, tmp_path) -> None:
    with pytest.raises(ArchiveReadError, match="cannot be extracted safely"):
        extract_archive_entry(
            "models.7z",
            entry_path,
            tmp_path / "entry.bin",
            command="missing-command",
            timeout_seconds=10,
            max_output_bytes=1024,
        )
