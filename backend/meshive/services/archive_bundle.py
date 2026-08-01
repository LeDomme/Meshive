import logging
import os
import tarfile
import threading
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BundleArchive:
    path: Path
    filename: str
    size_bytes: int
    modified_at: int


def stream_archive_bundle(
    archives: Sequence[BundleArchive],
) -> Generator[bytes, None, None]:
    """Stream existing archives inside an uncompressed TAR without temporary files."""
    read_fd, write_fd = os.pipe()

    def produce() -> None:
        try:
            with os.fdopen(write_fd, "wb") as output:
                with tarfile.open(
                    fileobj=output,
                    mode="w|",
                    format=tarfile.PAX_FORMAT,
                ) as bundle:
                    used_names: set[str] = set()
                    for archive in archives:
                        name = _unique_name(archive.filename, used_names)
                        info = tarfile.TarInfo(name=name)
                        info.size = archive.size_bytes
                        info.mtime = archive.modified_at
                        info.mode = 0o644
                        with archive.path.open("rb") as source:
                            bundle.addfile(info, source)
        except BrokenPipeError:
            # Expected when a browser cancels a large download.
            return
        except Exception:
            logger.exception("Archive bundle stream failed")

    producer = threading.Thread(
        target=produce,
        name="meshive-archive-bundle",
        daemon=True,
    )
    producer.start()
    output = os.fdopen(read_fd, "rb")
    try:
        while chunk := output.read(1024 * 1024):
            yield chunk
    finally:
        output.close()
        producer.join(timeout=5)


def _unique_name(filename: str, used_names: set[str]) -> str:
    candidate = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if candidate in {"", ".", ".."}:
        candidate = "archive"
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    counter = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    used_names.add(candidate.casefold())
    return candidate
