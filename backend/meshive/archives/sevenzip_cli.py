import os
import queue
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


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


def extract_archive_entry(
    archive_path: str,
    entry_path: str,
    destination_path: Path,
    *,
    command: str,
    timeout_seconds: int,
    max_output_bytes: int,
) -> int:
    if (
        not entry_path
        or entry_path.startswith("@")
        or any(character in entry_path for character in ("\x00", "\r", "\n", "*", "?"))
    ):
        raise ArchiveReadError("Archive entry path cannot be extracted safely")

    environment = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    return _run_bounded_extraction(
        [
            command,
            "x",
            "-so",
            "-bd",
            "-bb0",
            "-y",
            "--",
            archive_path,
            entry_path,
        ],
        destination_path=destination_path,
        environment=environment,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
        command_name=command,
    )


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


def _run_bounded_extraction(
    arguments: Sequence[str],
    *,
    destination_path: Path,
    environment: dict[str, str],
    timeout_seconds: float,
    max_output_bytes: int,
    command_name: str,
) -> int:
    if max_output_bytes <= 0:
        raise ArchiveReadError("Archive extraction output limit must be positive")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
    except FileNotFoundError as error:
        raise ArchiveReadError(
            f"Archive command {command_name!r} was not found"
        ) from error

    if process.stdout is None or process.stderr is None:  # pragma: no cover
        process.kill()
        raise ArchiveReadError("Archive command output could not be captured")

    chunks: queue.Queue[tuple[str, bytes | BaseException | None]] = queue.Queue(
        maxsize=16
    )
    stopping = threading.Event()

    def deliver(stream_name: str, item: bytes | BaseException | None) -> None:
        while not stopping.is_set():
            try:
                chunks.put((stream_name, item), timeout=0.1)
                return
            except queue.Full:
                continue

    def read_stream(stream_name: str, stream) -> None:
        try:
            while chunk := stream.read(64 * 1024):
                deliver(stream_name, chunk)
        except BaseException as error:  # pragma: no cover - OS-level pipe failure
            deliver(stream_name, error)
        finally:
            deliver(stream_name, None)

    readers = [
        threading.Thread(
            target=read_stream,
            args=("stdout", process.stdout),
            daemon=True,
        ),
        threading.Thread(
            target=read_stream,
            args=("stderr", process.stderr),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + timeout_seconds
    completed_streams: set[str] = set()
    stderr = bytearray()
    written = 0
    succeeded = False

    try:
        with destination_path.open("wb") as destination:
            while len(completed_streams) < 2:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, timeout_seconds)
                try:
                    stream_name, item = chunks.get(timeout=remaining)
                except queue.Empty as error:
                    raise subprocess.TimeoutExpired(
                        arguments, timeout_seconds
                    ) from error
                if item is None:
                    completed_streams.add(stream_name)
                    continue
                if isinstance(item, BaseException):
                    raise ArchiveReadError(
                        "Archive command output could not be read"
                    ) from item
                if stream_name == "stderr":
                    stderr.extend(item)
                    if len(stderr) > 64 * 1024:
                        del stderr[: len(stderr) - 64 * 1024]
                    continue
                written += len(item)
                if written > max_output_bytes:
                    raise ArchiveReadError(
                        "Archive entry exceeds the configured "
                        f"{max_output_bytes} byte extraction limit"
                    )
                destination.write(item)

        remaining = deadline - time.monotonic()
        process.wait(timeout=max(remaining, 0.001))
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[-2000:]
            raise ArchiveReadError(
                detail or f"7-Zip exited with status {process.returncode}"
            )
        succeeded = True
        return written
    except subprocess.TimeoutExpired as error:
        raise ArchiveReadError(
            f"Archive extraction exceeded the {timeout_seconds} second limit"
        ) from error
    finally:
        stopping.set()
        if process.poll() is None:
            process.kill()
        process.wait()
        for reader in readers:
            reader.join(timeout=1)
        if not succeeded:
            destination_path.unlink(missing_ok=True)


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
