"""Download provenance records.

Context.md §33 requires every experiment to record its dataset source, version
and extraction date; §32.7 names data-version drift as a top engineering risk.
Biomedical databases are updated continuously and several of them publish only
a "current" URL with no version in the path — Reactome's
``/download/current/`` is the clearest example. Without a record written at
fetch time, a re-run silently produces different numbers and the earlier result
becomes unreproducible.

Each downloaded file gets a sibling ``<file>.manifest.json``, and every fetch
appends one line to ``data/raw/_manifest.jsonl``. Manifests are committed to
git (see ``.gitignore``) even though the data itself is not: the manifest *is*
the reproducibility record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from target_prioritization.utils.paths import RAW_MANIFEST_LOG, ensure_dir, relative_to_root

__all__ = [
    "MANIFEST_SUFFIX",
    "Manifest",
    "append_manifest_log",
    "manifest_path_for",
    "read_manifest",
    "sha256_file",
    "verify_file",
    "write_manifest",
]

MANIFEST_SUFFIX = ".manifest.json"

# 1 MiB. Large enough to keep syscall overhead negligible on multi-hundred-MB
# parquet parts, small enough to stay out of the way in memory.
_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(slots=True)
class Manifest:
    """Provenance record for one downloaded file.

    Attributes:
        source: Logical source name, e.g. ``"open_targets"`` or ``"string"``.
        dataset: Dataset within the source, e.g. ``"target"``.
        url: Exact URL fetched.
        path: Destination path, relative to the project root.
        bytes: Size on disk.
        sha256: Checksum of the stored file.
        fetched_at: UTC ISO-8601 timestamp of the fetch.
        release: Upstream release tag when the source publishes one.
        version_pinned: False when the URL has no version in it (Reactome's
            ``current/``). For those, *fetched_at* is the only version anchor,
            so re-running later may yield different data.
        license: Upstream licence, recorded so downstream reuse stays lawful.
        checksum_verified_against: Upstream checksum manifest used to verify
            this file, when the provider publishes one.
    """

    source: str
    dataset: str
    url: str
    path: str
    bytes: int
    sha256: str
    fetched_at: str
    release: str | None = None
    version_pinned: bool = True
    license: str | None = None
    checksum_verified_against: str | None = None
    notes: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sha256_file(path: Path, *, chunk_bytes: int = _HASH_CHUNK_BYTES) -> str:
    """Streaming SHA-256 of *path*.

    Streamed rather than read whole: individual Open Targets parquet parts run
    to ~87 MB and the full pull is ~2.5 GB.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path_for(path: Path) -> Path:
    """Sibling manifest path for a data file."""
    return path.with_name(path.name + MANIFEST_SUFFIX)


def build_manifest(
    path: Path,
    *,
    source: str,
    dataset: str,
    url: str,
    release: str | None = None,
    version_pinned: bool = True,
    license: str | None = None,
    checksum_verified_against: str | None = None,
    notes: str | None = None,
    extra: dict[str, str] | None = None,
) -> Manifest:
    """Build a :class:`Manifest` by inspecting *path* on disk."""
    return Manifest(
        source=source,
        dataset=dataset,
        url=url,
        path=relative_to_root(path),
        bytes=path.stat().st_size,
        sha256=sha256_file(path),
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        release=release,
        version_pinned=version_pinned,
        license=license,
        checksum_verified_against=checksum_verified_against,
        notes=notes,
        extra=extra or {},
    )


def write_manifest(path: Path, manifest: Manifest) -> Path:
    """Write the sidecar manifest for *path* and append to the global log."""
    target = manifest_path_for(path)
    target.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n")
    append_manifest_log(manifest)
    return target


def read_manifest(path: Path) -> Manifest | None:
    """Read the sidecar manifest for *path*, or None if absent or unreadable."""
    manifest_file = manifest_path_for(path)
    if not manifest_file.exists():
        return None
    try:
        payload = json.loads(manifest_file.read_text())
    except json.JSONDecodeError:
        return None
    # Drop unknown keys so a manifest written by a newer version still loads.
    known = set(Manifest.__dataclass_fields__)
    return Manifest(**{k: v for k, v in payload.items() if k in known})


def append_manifest_log(manifest: Manifest, log_path: Path | None = None) -> None:
    """Append *manifest* as one JSON line to the append-only provenance log."""
    log_path = log_path or RAW_MANIFEST_LOG
    ensure_dir(log_path.parent)
    with log_path.open("a") as handle:
        handle.write(json.dumps(manifest.to_dict(), sort_keys=True) + "\n")


def verify_file(path: Path, expected_sha256: str | None = None) -> tuple[bool, str]:
    """Verify *path* against a checksum.

    Args:
        path: File to verify.
        expected_sha256: Checksum to compare against. When omitted, the value
            recorded in the sidecar manifest is used.

    Returns:
        ``(ok, detail)`` — *detail* explains the outcome either way, so callers
        can surface a specific reason rather than a bare False.
    """
    if not path.exists():
        return False, "file missing"

    if expected_sha256 is None:
        manifest = read_manifest(path)
        if manifest is None:
            return False, "no manifest and no expected checksum"
        expected_sha256 = manifest.sha256
        if manifest.bytes != path.stat().st_size:
            return False, f"size mismatch: manifest {manifest.bytes} vs disk {path.stat().st_size}"

    actual = sha256_file(path)
    if actual != expected_sha256:
        return False, f"sha256 mismatch: expected {expected_sha256[:12]}…, got {actual[:12]}…"
    return True, "ok"
