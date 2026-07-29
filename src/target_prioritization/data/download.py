"""Dataset download with resume, checksum verification and provenance.

Design notes:

* **Raw data is immutable** (Context.md §34). Files land in ``data/raw/<source>/``
  and are never rewritten in place. Re-running is idempotent: a file whose
  sidecar manifest still verifies is skipped.
* **Partial downloads resume.** The core profile is ~2.5 GB across ~50 files,
  several of them ~87 MB parquet parts. Bytes arrive in a ``.part`` file and
  are only promoted to the final name once the transfer completes, so an
  interrupted run can never leave a truncated file that looks complete.
* **Open Targets checksums are verified against upstream.** The release
  publishes ``release_data_integrity`` — a SHA-1 manifest covering every file
  in the release — and ``release_data_integrity.sha1``, the checksum of that
  manifest. Both are checked, so corruption in transit is detected rather than
  assumed away.
* **Rate limits are respected** (Context.md §34). Concurrency is bounded and
  retries back off exponentially.
"""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from target_prioritization.config import DatasetSpec, DataSourcesConfig, SourceSpec, settings
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_RAW, ensure_dir, relative_to_root
from target_prioritization.utils.provenance import (
    build_manifest,
    read_manifest,
    verify_file,
    write_manifest,
)

__all__ = [
    "DownloadItem",
    "DownloadResult",
    "DownloadStats",
    "IntegrityManifest",
    "discover_parquet_parts",
    "download_all",
    "expand_items",
    "plan_datasets",
    "verify_downloads",
]

log = get_logger(__name__)

# Apache autoindex links. Excludes the `?C=N;O=D` column-sort links and the
# absolute-path "Parent Directory" link.
_HREF_RE = re.compile(r'href="(?!/|\?|\.\.)([^"]+\.parquet)"', re.IGNORECASE)

_CHUNK_BYTES = 1024 * 1024
_TIMEOUT = httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=30.0)
_USER_AGENT = "disease-target-prioritization/0.1 (research; +https://github.com/)"


class DownloadError(RuntimeError):
    """A download failed after exhausting retries, or failed verification."""


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PlannedDataset:
    """A dataset selected for download, before its file list is known."""

    source_name: str
    source: SourceSpec
    dataset: DatasetSpec
    url: str
    dest_dir: Path

    @property
    def approx_bytes(self) -> int:
        return int(self.dataset.approx_mb * 1024 * 1024)


@dataclass(slots=True)
class DownloadItem:
    """A single file to fetch."""

    source_name: str
    dataset_name: str
    url: str
    dest: Path
    source: SourceSpec
    dataset: DatasetSpec
    # Path relative to the Open Targets release root, used to look up the
    # upstream SHA-1. None for non-Open-Targets sources.
    integrity_key: str | None = None


@dataclass(slots=True)
class DownloadResult:
    item: DownloadItem
    status: str  # "downloaded" | "skipped" | "failed"
    bytes_written: int = 0
    detail: str = ""


@dataclass(slots=True)
class DownloadStats:
    results: list[DownloadResult] = field(default_factory=list)

    @property
    def downloaded(self) -> list[DownloadResult]:
        return [r for r in self.results if r.status == "downloaded"]

    @property
    def skipped(self) -> list[DownloadResult]:
        return [r for r in self.results if r.status == "skipped"]

    @property
    def failed(self) -> list[DownloadResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def bytes_written(self) -> int:
        return sum(r.bytes_written for r in self.results)


def plan_datasets(
    config: DataSourcesConfig,
    profile: str,
    only: list[str] | None = None,
) -> list[PlannedDataset]:
    """Select datasets for *profile*, optionally filtered by *only*.

    Args:
        config: Parsed ``data_sources.yaml``.
        profile: ``core`` or ``full``.
        only: Names to keep. Each entry matches a source (``string``) or a
            specific dataset (``open_targets/target``).

    Raises:
        KeyError: If an *only* entry matches nothing — a typo there would
            otherwise silently download less than the user asked for.
    """
    planned = [
        PlannedDataset(
            source_name=source_name,
            source=source,
            dataset=dataset,
            url=source.dataset_url(dataset),
            dest_dir=DATA_RAW / source_name,
        )
        for source_name, source, dataset in config.select(profile)
    ]

    if not only:
        return planned

    wanted = {name.strip() for name in only if name.strip()}
    selected = [
        p
        for p in planned
        if p.source_name in wanted or f"{p.source_name}/{p.dataset.name}" in wanted
    ]
    matched = {p.source_name for p in selected} | {
        f"{p.source_name}/{p.dataset.name}" for p in selected
    }
    if unmatched := wanted - matched:
        available = sorted({p.source_name for p in planned})
        raise KeyError(
            f"--only matched nothing for {sorted(unmatched)}. "
            f"Available sources in profile {profile!r}: {available}"
        )
    return selected


# ---------------------------------------------------------------------------
# Open Targets release integrity manifest
# ---------------------------------------------------------------------------


class IntegrityManifest:
    """SHA-1 checksums published with an Open Targets release.

    The release root holds ``release_data_integrity`` (``<sha1>  ./path`` lines
    covering every file) and ``release_data_integrity.sha1`` (the checksum of
    that manifest). Verifying the manifest before trusting it closes the
    obvious hole.
    """

    def __init__(self, checksums: dict[str, str], source_url: str) -> None:
        self._checksums = checksums
        self.source_url = source_url

    def __len__(self) -> int:
        return len(self._checksums)

    def sha1_for(self, relative_path: str) -> str | None:
        # removeprefix, not lstrip: lstrip("./") takes a character *set* and
        # would eat leading dots from a legitimately dot-prefixed name.
        return self._checksums.get(relative_path.removeprefix("./"))

    @classmethod
    def fetch(cls, manifest_url: str, client: httpx.Client) -> IntegrityManifest | None:
        """Download and verify the manifest. Returns None if unavailable.

        A missing manifest is not fatal — downloads still get our own SHA-256
        recorded — but it is logged as a warning because it weakens the
        guarantee.
        """
        try:
            response = client.get(manifest_url)
            response.raise_for_status()
            body = response.text

            # The published checksum of the manifest itself.
            expected = None
            try:
                sha_response = client.get(manifest_url + ".sha1")
                sha_response.raise_for_status()
                expected = sha_response.text.split()[0].strip()
            except (httpx.HTTPError, IndexError):
                log.warning("integrity_manifest_checksum_unavailable", url=manifest_url)

            if expected:
                actual = hashlib.sha1(response.content).hexdigest()
                if actual != expected:
                    log.error(
                        "integrity_manifest_corrupt",
                        url=manifest_url,
                        expected=expected,
                        actual=actual,
                    )
                    return None

            checksums = {}
            for line in body.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    checksums[parts[1].strip().removeprefix("./")] = parts[0].strip()

            # A one-line "manifest" means the URL points at the .sha1 checksum
            # file rather than the manifest it describes. Silently accepting it
            # would leave every download unverified while still looking fine.
            if len(checksums) < 100:
                log.error(
                    "integrity_manifest_too_small",
                    url=manifest_url,
                    entries=len(checksums),
                    note="expected ~37k entries; check checksum_manifest_url in data_sources.yaml",
                )
                return None

            log.info("integrity_manifest_loaded", entries=len(checksums), verified=bool(expected))
            return cls(checksums, manifest_url)

        except httpx.HTTPError as exc:
            log.warning("integrity_manifest_unavailable", url=manifest_url, error=str(exc))
            return None


def _sha1_file(path: Path) -> str:
    digest = hashlib.sha1()  # upstream publishes SHA-1, not our choice
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Directory expansion
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def discover_parquet_parts(dir_url: str, client: httpx.Client) -> list[str]:
    """List ``.parquet`` filenames in an Apache autoindex directory.

    Open Targets 26.06 mixes two naming conventions — Spark-partitioned
    ``part-00000-<uuid>-c000.snappy.parquet`` and single-file
    ``<dataset>.parquet`` — so matching on the extension rather than a ``part-``
    prefix is what keeps both working.
    """
    response = client.get(dir_url)
    response.raise_for_status()
    names = sorted(set(_HREF_RE.findall(response.text)))
    if not names:
        raise DownloadError(f"No .parquet files found at {dir_url}")
    return names


def expand_items(
    planned: list[PlannedDataset],
    client: httpx.Client,
) -> list[DownloadItem]:
    """Resolve planned datasets into concrete files to fetch."""
    items: list[DownloadItem] = []

    for entry in planned:
        if entry.source.kind == "files":
            filename = entry.dataset.filename or entry.url.rsplit("/", 1)[-1]
            items.append(
                DownloadItem(
                    source_name=entry.source_name,
                    dataset_name=entry.dataset.name,
                    url=entry.url,
                    dest=entry.dest_dir / filename,
                    source=entry.source,
                    dataset=entry.dataset,
                )
            )
            continue

        # parquet_dir: list the directory, keep the dataset name as a subdir
        # so the partitioned parts stay grouped and readable by pyarrow/duckdb.
        log.info("listing_dataset", source=entry.source_name, dataset=entry.dataset.name)
        for name in discover_parquet_parts(entry.url, client):
            items.append(
                DownloadItem(
                    source_name=entry.source_name,
                    dataset_name=entry.dataset.name,
                    url=entry.url.rstrip("/") + "/" + name,
                    dest=entry.dest_dir / entry.dataset.name / name,
                    source=entry.source,
                    dataset=entry.dataset,
                    integrity_key=f"output/{entry.dataset.name}/{name}",
                )
            )

    return items


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type((httpx.HTTPError, DownloadError)),
    reraise=True,
)
def _stream_to_disk(url: str, dest: Path, client: httpx.Client) -> int:
    """Stream *url* to *dest*, resuming a partial ``.part`` file if present.

    Returns the number of bytes in the completed file.
    """
    ensure_dir(dest.parent)
    part = dest.with_name(dest.name + ".part")
    resume_from = part.stat().st_size if part.exists() else 0

    headers = {"User-Agent": _USER_AGENT}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"

    with client.stream("GET", url, headers=headers) as response:
        # 416 means the .part is already at or past the full length — most
        # likely a complete file left behind by a crash between write and
        # rename. Restart it rather than guess.
        if response.status_code == 416 and resume_from:
            part.unlink(missing_ok=True)
            raise DownloadError(f"stale partial file for {url}; restarting")

        response.raise_for_status()

        # The server ignored the Range header, so restart from zero.
        append = response.status_code == 206
        if resume_from and not append:
            resume_from = 0

        mode = "ab" if append and resume_from else "wb"
        with part.open(mode) as handle:
            for chunk in response.iter_bytes(_CHUNK_BYTES):
                handle.write(chunk)

    size = part.stat().st_size
    if size == 0:
        part.unlink(missing_ok=True)
        raise DownloadError(f"empty response body for {url}")

    # Atomic promotion: the final name never exists in a truncated state.
    part.replace(dest)
    return size


def _fetch_one(
    item: DownloadItem,
    client: httpx.Client,
    integrity: IntegrityManifest | None,
    *,
    force: bool = False,
) -> DownloadResult:
    """Fetch one file, skipping it if the existing copy still verifies."""
    if not force and item.dest.exists():
        ok, detail = verify_file(item.dest)
        if ok:
            return DownloadResult(item, "skipped", detail="already present and verified")
        if read_manifest(item.dest) is None:
            # Present but unaccounted for. Re-fetch rather than trust it.
            log.warning("redownloading_unmanifested_file", path=relative_to_root(item.dest))
        else:
            log.warning(
                "redownloading_failed_verification",
                path=relative_to_root(item.dest),
                detail=detail,
            )

    try:
        size = _stream_to_disk(item.url, item.dest, client)
    except (httpx.HTTPError, DownloadError) as exc:
        return DownloadResult(item, "failed", detail=f"{type(exc).__name__}: {exc}")

    # Verify against the upstream checksum where one is published.
    verified_against: str | None = None
    if integrity and item.integrity_key:
        expected_sha1 = integrity.sha1_for(item.integrity_key)
        if expected_sha1:
            actual_sha1 = _sha1_file(item.dest)
            if actual_sha1 != expected_sha1:
                item.dest.unlink(missing_ok=True)
                return DownloadResult(
                    item,
                    "failed",
                    detail=f"upstream sha1 mismatch (expected {expected_sha1[:12]}…)",
                )
            verified_against = integrity.source_url
        else:
            log.debug("no_upstream_checksum", key=item.integrity_key)

    manifest = build_manifest(
        item.dest,
        source=item.source_name,
        dataset=item.dataset_name,
        url=item.url,
        release=item.source.release,
        version_pinned=item.source.release_pinned,
        license=item.source.license,
        checksum_verified_against=verified_against,
        notes=item.dataset.leakage_note,
    )
    write_manifest(item.dest, manifest)

    return DownloadResult(item, "downloaded", bytes_written=size)


def download_all(
    items: list[DownloadItem],
    *,
    concurrency: int | None = None,
    force: bool = False,
    integrity: IntegrityManifest | None = None,
    client: httpx.Client | None = None,
) -> DownloadStats:
    """Fetch *items* concurrently, returning per-file outcomes.

    Failures are collected rather than raised so that one dead URL does not
    abandon a 2.5 GB pull. The caller decides what a partial success means.
    """
    concurrency = concurrency or settings.download_concurrency
    stats = DownloadStats()
    owns_client = client is None
    client = client or httpx.Client(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_fetch_one, item, client, integrity, force=force): item
                for item in items
            }
            for done, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                stats.results.append(result)

                event = {
                    "downloaded": "fetched",
                    "skipped": "skipped",
                    "failed": "fetch_failed",
                }[result.status]
                logger = log.error if result.status == "failed" else log.info
                logger(
                    event,
                    progress=f"{done}/{len(items)}",
                    source=result.item.source_name,
                    dataset=result.item.dataset_name,
                    file=result.item.dest.name,
                    mb=round(result.bytes_written / 1048576, 1) or None,
                    detail=result.detail or None,
                )
    finally:
        if owns_client:
            client.close()

    return stats


def verify_downloads(
    root: Path | None = None,
    *,
    integrity: IntegrityManifest | None = None,
) -> tuple[list[Path], list[tuple[Path, str]], int]:
    """Re-verify every downloaded file.

    Each file is checked against the SHA-256 recorded in its own manifest,
    which detects local corruption. When *integrity* is supplied, Open Targets
    files are additionally checked against the SHA-1 published with the
    release — that is the stronger check, because it validates against upstream
    rather than against a hash we computed ourselves from possibly-bad bytes.

    Args:
        root: Directory to scan. Defaults to ``data/raw``.
        integrity: Open Targets release manifest, when available.

    Returns:
        ``(ok_paths, failures, n_upstream_verified)``.
    """
    root = root or DATA_RAW
    ok: list[Path] = []
    failures: list[tuple[Path, str]] = []
    upstream_verified = 0

    for manifest_file in sorted(root.rglob("*.manifest.json")):
        data_path = manifest_file.with_name(manifest_file.name.removesuffix(".manifest.json"))

        passed, detail = verify_file(data_path)
        if not passed:
            failures.append((data_path, detail))
            continue

        if integrity is not None:
            record = read_manifest(data_path)
            if record and record.source == "open_targets":
                key = f"output/{record.dataset}/{data_path.name}"
                expected_sha1 = integrity.sha1_for(key)
                if expected_sha1:
                    if _sha1_file(data_path) != expected_sha1:
                        failures.append((data_path, "upstream sha1 mismatch"))
                        continue
                    upstream_verified += 1

        ok.append(data_path)

    return ok, failures, upstream_verified
