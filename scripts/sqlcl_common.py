#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
import hashlib
import html
import json
import re
import urllib.error
import urllib.request
import urllib.parse
import zipfile

LATEST_URL = "https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-latest.zip"
DOWNLOAD_PAGE_URL = "https://www.oracle.com/database/sqldeveloper/technologies/sqlcl/download/"
VERSION_URL_TEMPLATE = "https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-{version}.zip"
USER_AGENT = "sqlcl-aqua-registry/1.0 (+https://github.com/jlyle/sqlcl-aqua-registry)"


@dataclass(frozen=True)
class PublishedDownload:
    version: str
    url: str
    md5: str | None
    sha1: str | None
    sha256: str | None
    release_date: str | None


@dataclass(frozen=True)
class ReleaseMetadata:
    version: str
    oracle_url: str
    oracle_release_asset_url: str
    oracle_release_page_url: str
    release_date: str | None
    md5: str
    sha1: str
    sha256: str
    oracle_published_md5: str | None
    oracle_published_sha1: str | None
    oracle_published_sha256: str | None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def request(url: str, method: str = "GET", headers: dict[str, str] | None = None) -> urllib.request.Request:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    return urllib.request.Request(url, headers=request_headers, method=method)


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(request(url), timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request(url), timeout=300) as response:
        with destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)


def hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_download_page(page_html: str, expected_url: str | None = None) -> PublishedDownload:
    normalized = html.unescape(page_html)
    expected_version = _version_from_download_url(expected_url) if expected_url else None

    for match in _download_link_matches(normalized):
        url = _normalize_oracle_url(match.group("url"))
        version = match.group("version")
        if expected_version and version != expected_version:
            continue

        chunk = normalized[max(0, match.start() - 2500) : match.end() + 2500]
        md5, sha1, sha256 = _checksums_from_chunk(chunk)
        release_date = _release_date_from_chunk(chunk)
        if md5 or sha1 or sha256:
            return PublishedDownload(
                version=version,
                url=url,
                md5=md5.lower() if md5 else None,
                sha1=sha1.lower() if sha1 else None,
                sha256=sha256.lower() if sha256 else None,
                release_date=release_date,
            )

    if expected_url and expected_version:
        md5, sha1, sha256 = _checksums_from_chunk(normalized)
        if md5 or sha1 or sha256:
            return PublishedDownload(
                version=expected_version,
                url=_normalize_oracle_url(expected_url),
                md5=md5.lower() if md5 else None,
                sha1=sha1.lower() if sha1 else None,
                sha256=sha256.lower() if sha256 else None,
                release_date=_release_date_from_chunk(normalized),
            )

    raise RuntimeError("Could not find a SQLcl download row with published checksums on Oracle's page")


def extract_version_from_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        try:
            version_text = archive.read("sqlcl/bin/version.txt").decode("utf-8", errors="replace")
        except KeyError:
            version_text = ""

        release = _first_group(r"^RELEASE=([0-9]+(?:\.[0-9]+)+)\s*$", version_text, flags=re.MULTILINE)
        if release:
            return release

        version_files = []
        for name in archive.namelist():
            match = re.fullmatch(r"sqlcl/([0-9]+(?:\.[0-9]+)+)", name)
            if match:
                version_files.append(match.group(1))
        if len(version_files) == 1:
            return version_files[0]

    raise RuntimeError(f"Could not determine SQLcl version from {zip_path}")


def verify_published_checksums(zip_path: Path, published: PublishedDownload, asset_url: str, page_url: str) -> ReleaseMetadata:
    md5 = hash_file(zip_path, "md5")
    sha1 = hash_file(zip_path, "sha1")
    sha256 = hash_file(zip_path, "sha256")

    mismatches = []
    if published.md5 and published.md5 != md5:
        mismatches.append(f"MD5 expected {published.md5}, got {md5}")
    if published.sha1 and published.sha1 != sha1:
        mismatches.append(f"SHA1 expected {published.sha1}, got {sha1}")
    if published.sha256 and published.sha256 != sha256:
        mismatches.append(f"SHA256 expected {published.sha256}, got {sha256}")
    if mismatches:
        raise RuntimeError("Oracle checksum verification failed: " + "; ".join(mismatches))
    if not any([published.md5, published.sha1, published.sha256]):
        raise RuntimeError("Oracle did not publish any supported checksum for the current SQLcl download")

    return ReleaseMetadata(
        version=published.version,
        oracle_url=published.url,
        oracle_release_asset_url=asset_url,
        oracle_release_page_url=page_url,
        release_date=published.release_date,
        md5=md5,
        sha1=sha1,
        sha256=sha256,
        oracle_published_md5=published.md5,
        oracle_published_sha1=published.sha1,
        oracle_published_sha256=published.sha256,
    )


def write_checksum_files(output_dir: Path, metadata: ReleaseMetadata) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"sqlcl-{metadata.version}.zip"
    files = {
        f"{archive_name}.md5": metadata.md5,
        f"{archive_name}.sha1": metadata.sha1,
        f"{archive_name}.sha256": metadata.sha256,
    }
    written = []
    for filename, checksum in files.items():
        path = output_dir / filename
        path.write_text(f"{checksum}  {archive_name}\n", encoding="utf-8")
        written.append(path)

    checksums = output_dir / f"sqlcl-{metadata.version}.checksums.txt"
    checksums.write_text(
        "\n".join(
            [
                f"md5    {metadata.md5}  {archive_name}",
                f"sha1   {metadata.sha1}  {archive_name}",
                f"sha256 {metadata.sha256}  {archive_name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(checksums)
    return written


def write_release_notes(output_dir: Path, metadata: ReleaseMetadata) -> Path:
    path = output_dir / "release-notes.md"
    lines = [
        f"# SQLcl {metadata.version}",
        "",
        "This is a metadata-only release for version discovery and checksum verification.",
        "The SQLcl zip archive is not mirrored here.",
        "Installs need to be downloaded directly from Oracle.",
        "",
        f"- Oracle versioned download: {metadata.oracle_url}",
        f"- Oracle download page checked: {metadata.oracle_release_page_url}",
    ]
    if metadata.release_date:
        lines.append(f"- Oracle release date: {metadata.release_date}")
    lines.extend(
        [
            "",
            "## Checksums",
            "",
            "| Algorithm | Checksum |",
            "| --- | --- |",
            f"| MD5 | `{metadata.md5}` |",
            f"| SHA1 | `{metadata.sha1}` |",
            f"| SHA256 | `{metadata.sha256}` |",
            "",
            "Oracle-published checksum verification passed before this release was created.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_metadata(output_dir: Path, metadata: ReleaseMetadata) -> Path:
    path = output_dir / f"sqlcl-{metadata.version}.metadata.json"
    metadata_json = metadata.to_json()
    path.write_text(metadata_json, encoding="utf-8")
    (output_dir / "metadata.json").write_text(metadata_json, encoding="utf-8")
    return path


def write_env_file(output_dir: Path, metadata: ReleaseMetadata) -> Path:
    path = output_dir / "release.env"
    path.write_text(
        "\n".join(
            [
                f"VERSION={metadata.version}",
                f"ORACLE_URL={metadata.oracle_url}",
                f"MD5={metadata.md5}",
                f"SHA1={metadata.sha1}",
                f"SHA256={metadata.sha256}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def append_github_output(path: Path, pairs: Iterable[tuple[str, str]]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in pairs:
            output.write(f"{key}={value}\n")


def _first_group(pattern: str, text: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1) if match else None


def _checksums_from_chunk(chunk: str) -> tuple[str | None, str | None, str | None]:
    md5 = sha1 = sha256 = None
    checksum_re = re.compile(
        r"\b(?:MD5|SHA[-\s]?(?:1|256))\s*:?\s*(?:md)?([A-Fa-f0-9]{32,64})",
        re.IGNORECASE,
    )
    for match in checksum_re.finditer(chunk):
        checksum = match.group(1).lower()
        if len(checksum) == 32:
            md5 = checksum
        elif len(checksum) == 40:
            sha1 = checksum
        elif len(checksum) == 64:
            sha256 = checksum
    return md5, sha1, sha256


def _download_link_matches(page_html: str) -> Iterable[re.Match[str]]:
    link_re = re.compile(
        r"""href\s*=\s*["']\s*(?P<url>(?:https?:)?\s*//download\.oracle\.com/[^"']*?/sqlcl-(?P<version>\d+(?:\.\d+)+)\.zip)\s*["']""",
        re.IGNORECASE,
    )
    return link_re.finditer(page_html)


def _normalize_oracle_url(url: str) -> str:
    normalized = re.sub(r"\s+", "", url.strip())
    if normalized.startswith("//"):
        return f"https:{normalized}"
    if normalized.startswith("http://"):
        return "https://" + normalized[len("http://") :]
    return normalized


def _version_from_download_url(url: str | None) -> str | None:
    if not url:
        return None
    normalized = _normalize_oracle_url(url)
    parsed = urllib.parse.urlparse(normalized)
    match = re.search(r"sqlcl-(\d+(?:\.\d+)+)\.zip$", parsed.path)
    return match.group(1) if match else None


def _release_date_from_chunk(chunk: str) -> str | None:
    release_date = _first_group(r"Release Date:\s*([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})", chunk)
    if release_date:
        return release_date.strip()

    version_date = _first_group(
        r"Version\s+\d+(?:\.\d+)+\s*-\s*([^<\n\r]+)",
        chunk,
        flags=re.IGNORECASE,
    )
    if version_date:
        return re.sub(r"\s+", " ", version_date).strip()
    return None
