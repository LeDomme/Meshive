import os
import sys

import pytest

from meshive.archives.sevenzip_cli import (
    ArchiveReadError,
    _run_bounded_command,
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
