import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Sequence


class ArchiveReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ListedArchiveEntry:
    path: str
    name: str
    is_directory: bool
    size_bytes: int | None
    compressed_size_bytes: int | None
    crc: str | None
    modified_at: str | None


def list_archive(
    archive_path: str,
    *,
    command: str,
    timeout_seconds: int,
    max_entries: int,
    max_output_bytes: int,
) -> list[ListedArchiveEntry]:
    environment = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    returncode, output = _run_bounded_command(
        [command, "l", "-slt", "-ba", "--", archive_path],
        environment=environment,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
        command_name=command,
    )

    if returncode != 0:
        detail = output.strip()[-2000:]
        raise ArchiveReadError(detail or f"7-Zip exited with status {returncode}")

    entries = parse_technical_listing(output)
    if len(entries) > max_entries:
        raise ArchiveReadError(
            f"Archive contains {len(entries)} entries; limit is {max_entries}"
        )
    return entries


def _run_bounded_command(
    arguments: Sequence[str],
    *,
    environment: dict[str, str],
    timeout_seconds: int,
    max_output_bytes: int,
    command_name: str,
) -> tuple[int, str]:
    try:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
        )
    except FileNotFoundError as error:
        raise ArchiveReadError(
            f"Archive command {command_name!r} was not found"
        ) from error

    if process.stdout is None:  # pragma: no cover - guaranteed by stdout=PIPE
        process.kill()
        raise ArchiveReadError("Archive command output could not be captured")

    chunks: queue.Queue[bytes | BaseException | None] = queue.Queue(maxsize=8)
    stopping = threading.Event()

    def deliver(item: bytes | BaseException | None) -> None:
        while not stopping.is_set():
            try:
                chunks.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def read_output() -> None:
        try:
            while chunk := process.stdout.read(64 * 1024):
                deliver(chunk)
        except BaseException as error:  # pragma: no cover - OS-level pipe failure
            deliver(error)
        finally:
            deliver(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    output = bytearray()

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(arguments, timeout_seconds)
            try:
                item = chunks.get(timeout=remaining)
            except queue.Empty as error:
                raise subprocess.TimeoutExpired(arguments, timeout_seconds) from error
            if item is None:
                break
            if isinstance(item, BaseException):
                raise ArchiveReadError("Archive command output could not be read") from item
            output.extend(item)
            if len(output) > max_output_bytes:
                raise ArchiveReadError(
                    "Archive listing output exceeds the configured "
                    f"{max_output_bytes} byte limit"
                )
        remaining = deadline - time.monotonic()
        process.wait(timeout=max(remaining, 0.001))
    except subprocess.TimeoutExpired as error:
        raise ArchiveReadError(
            f"Archive listing exceeded the {timeout_seconds} second limit"
        ) from error
    finally:
        stopping.set()
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join(timeout=1)

    return process.returncode, output.decode("utf-8", errors="replace")


def parse_technical_listing(output: str) -> list[ListedArchiveEntry]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        current[key.strip()] = value
    if current:
        records.append(current)

    entries: list[ListedArchiveEntry] = []
    seen: set[str] = set()
    for record in records:
        raw_path = record.get("Path")
        if not raw_path or ("Size" not in record and "Folder" not in record):
            continue
        path = PurePosixPath(raw_path.replace("\\", "/")).as_posix().lstrip("/")
        if not path or path in seen:
            continue
        seen.add(path)
        entries.append(
            ListedArchiveEntry(
                path=path,
                name=PurePosixPath(path).name,
                is_directory=record.get("Folder") == "+"
                or record.get("Attributes", "").startswith("D"),
                size_bytes=_optional_int(record.get("Size")),
                compressed_size_bytes=_optional_int(record.get("Packed Size")),
                crc=record.get("CRC") or None,
                modified_at=record.get("Modified") or None,
            )
        )
    return entries


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        return None
