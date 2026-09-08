#!/usr/bin/env python3
"""Fail-closed retention cleanup for a user-owned GHCR container package."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

DEV_TAG = re.compile(r"^(?:pr-|sha-)")
SEMVER_TAG = re.compile(r"^\d+(?:\.\d+){0,2}$")


class DiscoveryError(RuntimeError):
    """A safety-critical discovery operation was incomplete."""


@dataclass(frozen=True)
class Version:
    id: int
    digest: str
    tags: tuple[str, ...]
    created_at: dt.datetime


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def digest(value: str) -> str:
    return value if value.startswith("sha256:") else f"sha256:{value}"


def is_protected_tag(tag: str) -> bool:
    return tag in {"latest", "edge"} or bool(SEMVER_TAG.fullmatch(tag))


def is_dev_version(version: Version) -> bool:
    return bool(version.tags) and all(DEV_TAG.match(tag) for tag in version.tags)


def is_old(version: Version, cutoff: dt.datetime) -> bool:
    return version.created_at < cutoff


def resolve_dry_run(event_name: str, requested_dry_run: bool, schedule_delete_enabled: str | None) -> bool:
    """Scheduled deletion requires an explicit repository-variable opt-in."""
    if event_name == "schedule":
        return schedule_delete_enabled != "true"
    return requested_dry_run


def candidates(versions: Iterable[Version], protected_digests: set[str], cutoff: dt.datetime) -> tuple[list[Version], list[Version], int]:
    dev, orphaned, young = [], [], 0
    for version in versions:
        if not is_old(version, cutoff):
            young += 1
            continue
        if version.tags:
            if is_dev_version(version):
                dev.append(version)
            continue  # Protected and unknown tags are always retained.
        if digest(version.digest) not in protected_digests:
            orphaned.append(version)
    return dev, orphaned, young


class GitHubPackages:
    def __init__(self, owner: str, package: str, token: str):
        self.base = f"https://api.github.com/users/{owner}/packages/container/{package}/versions"
        self.token = token

    def request(self, url: str, method: str = "GET") -> tuple[Any, dict[str, str]]:
        request = urllib.request.Request(url, method=method, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read()
                return (json.loads(body) if body else None), dict(response.headers.items())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            raise DiscoveryError(f"GitHub Packages API {method} {url} failed: {error.code} {detail}") from error
        except urllib.error.URLError as error:
            raise DiscoveryError(f"GitHub Packages API {method} {url} failed: {error}") from error

    @staticmethod
    def version(raw: dict[str, Any]) -> Version:
        try:
            tags = tuple(raw["metadata"]["container"]["tags"])
            return Version(raw["id"], digest(raw["name"]), tags, parse_time(raw["created_at"]))
        except (KeyError, TypeError, ValueError) as error:
            raise DiscoveryError(f"Package version has an unexpected shape: {raw!r}") from error

    def list_versions(self) -> list[Version]:
        url = f"{self.base}?per_page=100"
        result: list[Version] = []
        while url:
            raw, headers = self.request(url)
            if not isinstance(raw, list):
                raise DiscoveryError("Package versions response was not a list")
            result.extend(self.version(item) for item in raw)
            url = next_link(headers.get("Link", ""))
        return result

    def get_version(self, version_id: int) -> Version:
        raw, _ = self.request(f"{self.base}/{version_id}")
        if not isinstance(raw, dict):
            raise DiscoveryError(f"Package version {version_id} response was not an object")
        return self.version(raw)

    def delete(self, version_id: int) -> None:
        self.request(f"{self.base}/{version_id}", "DELETE")


def next_link(header: str) -> str | None:
    for part in header.split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1:part.find(">")]
    return None


def inspect_manifest(image: str, reference: str) -> dict[str, Any]:
    try:
        output = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", "--raw", f"{image}@{reference}" if reference.startswith("sha256:") else f"{image}:{reference}"],
            check=True, capture_output=True, text=True,
        ).stdout
        parsed = json.loads(output)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise DiscoveryError(f"Unable to inspect protected OCI manifest {image}:{reference}") from error
    if not isinstance(parsed, dict):
        raise DiscoveryError(f"Protected OCI manifest {image}:{reference} was not an object")
    return parsed


def manifest_dependencies(manifest: dict[str, Any]) -> list[str]:
    """Buildx currently exposes platform and attestation children in manifests."""
    children = manifest.get("manifests", [])
    if not isinstance(children, list):
        raise DiscoveryError("OCI manifest children were not a list")
    if not all(isinstance(item, dict) and isinstance(item.get("digest"), str) for item in children):
        raise DiscoveryError("OCI manifest child descriptor was incomplete")
    dependencies = [item["digest"] for item in children]
    if "subject" not in manifest:
        return dependencies
    subject = manifest["subject"]
    if not isinstance(subject, dict) or not isinstance(subject.get("digest"), str):
        raise DiscoveryError("OCI manifest subject descriptor was incomplete")
    dependencies.append(subject["digest"])
    return dependencies


def protected_graph(versions: Iterable[Version], image: str) -> tuple[set[int], set[str]]:
    protected_versions: set[int] = set()
    discovered: set[str] = set()
    pending: list[str] = []
    for version in versions:
        protected_tags = [tag for tag in version.tags if is_protected_tag(tag)]
        if not protected_tags:
            continue
        protected_versions.add(version.id)
        pending.append(version.digest)
        for tag in protected_tags:
            pending.extend(manifest_dependencies(inspect_manifest(image, tag)))
    while pending:
        item = digest(pending.pop())
        if item in discovered:
            continue
        discovered.add(item)
        pending.extend(manifest_dependencies(inspect_manifest(image, item)))
    return protected_versions, discovered


def safe_to_delete(version: Version, protected_digests: set[str], cutoff: dt.datetime) -> bool:
    if not is_old(version, cutoff):
        return False
    if version.tags:
        return is_dev_version(version)
    return digest(version.digest) not in protected_digests


def delete_candidates(api: GitHubPackages, selected: Iterable[Version], protected_digests: set[str], cutoff: dt.datetime, dry_run: bool) -> int:
    deleted = 0
    for candidate in selected:
        current = api.get_version(candidate.id)  # Race-safe final API recheck.
        if not safe_to_delete(current, protected_digests, cutoff):
            print(f"SKIP {current.id}: tags changed or version is no longer eligible")
            continue
        print(f"{'WOULD DELETE' if dry_run else 'DELETE'} {current.id} {current.digest} tags={list(current.tags)}")
        if not dry_run:
            api.delete(current.id)
            deleted += 1
    return deleted


def write_summary(path: str, **values: Any) -> None:
    with open(path, "a", encoding="utf-8") as summary:
        summary.write("## GHCR cleanup\n\n| Metric | Count |\n| --- | ---: |\n")
        for key, value in values.items():
            summary.write(f"| {key.replace('_', ' ')} | {value} |\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--image", required=True, help="Full registry image reference, e.g. ghcr.io/ledomme/meshive")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--retention-days", type=int, default=7)
    arguments = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise DiscoveryError("GITHUB_TOKEN is required")
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=arguments.retention_days)
    api = GitHubPackages(arguments.owner, arguments.package, token)
    versions = api.list_versions()
    protected_versions, protected_digests = protected_graph(versions, arguments.image)
    dev, orphaned, young = candidates(versions, protected_digests, cutoff)
    deleted = delete_candidates(api, [*dev, *orphaned], protected_digests, cutoff, arguments.dry_run)
    write_summary(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"), total_package_versions=len(versions), protected_tagged_versions=len(protected_versions), protected_oci_digests=len(protected_digests), old_dev_candidates=len(dev), orphaned_untagged_candidates=len(orphaned), young_skipped_versions=young, deleted_versions=deleted, dry_run=arguments.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiscoveryError as error:
        print(f"::error::{error}\nNo package versions were deleted because discovery did not complete.", file=sys.stderr)
        raise SystemExit(1)
