#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
import hashlib
import json
import re
import urllib.error
import urllib.request
import urllib.parse
import zipfile

from bs4 import BeautifulSoup
from dateparser.search import search_dates

LATEST_URL = "https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-latest.zip"
DOWNLOAD_PAGE_URL = "https://www.oracle.com/database/sqldeveloper/technologies/sqlcl/download/"
VERSION_URL_TEMPLATE = "https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-{version}.zip"
# Oracle pages are more likely to serve full HTML reliably with a descriptive user agent.
USER_AGENT = "sqlcl-aqua-registry/1.0 (+https://github.com/jlyle/sqlcl-aqua-registry)"
DATE_SEARCH_SETTINGS = {
    "PARSERS": ["absolute-time"],
    "REQUIRE_PARTS": ["year", "month", "day"],
    "STRICT_PARSING": True,
}
VERSION_RE = re.compile(r"\b(?:\d+\.){4}\d+\b")
DOWNLOAD_VERSION_RE = re.compile(r"\bsqlcl-(\d+(?:\.\d+)+)\.zip\b")
MD5_RE = re.compile(r"\b[A-Fa-f0-9]{32}\b")
SHA1_RE = re.compile(r"\b[A-Fa-f0-9]{40}\b")
SHA256_RE = re.compile(r"\b[A-Fa-f0-9]{64}\b")
ZIP_LINK_RE = re.compile(r"\d\.zip\b", re.IGNORECASE)


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


def parse_download_page(page_html: str, page_url: str) -> PublishedDownload:
    soup = BeautifulSoup(page_html, "html.parser")
    page_text = _page_text(soup)

    version = _version_from_page(page_text)
    url = _url_from_page(soup, page_url) or _url_from_version(version)
    md5 = _md5_from_page(page_text)
    sha1 = _sha1_from_page(page_text)
    sha256 = _sha256_from_page(page_text)
    release_date = _release_date_from_page(page_text)

    if not version:
        raise RuntimeError("Could not find a SQLcl version on the Oracle download page")
    if not url:
        raise RuntimeError("Could not find a SQLcl download URL on the Oracle download page")

    return PublishedDownload(
        version=version,
        url=url,
        md5=md5,
        sha1=sha1,
        sha256=sha256,
        release_date=release_date,
    )


def extract_version_from_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        try:
            # Modern SQLcl archives include the build version here.
            version_text = archive.read("sqlcl/bin/version.txt").decode("utf-8", errors="replace")
        except KeyError:
            version_text = ""

        release = _first_group(r"^RELEASE=([0-9]+(?:\.[0-9]+)+)\s*$", version_text, flags=re.MULTILINE)
        if release:
            return release

        # Older/current archives also include a version-named marker file at
        # the top of the sqlcl directory. Use it only when unambiguous.
        version_files = []
        for name in archive.namelist():
            match = re.fullmatch(r"sqlcl/([0-9]+(?:\.[0-9]+)+)", name)
            if match:
                version_files.append(match.group(1))
        if len(version_files) == 1:
            return version_files[0]

    raise RuntimeError(f"Could not determine SQLcl version from {zip_path}")


def verify_published_checksums(zip_path: Path, published: PublishedDownload, asset_url: str, page_url: str) -> ReleaseMetadata:
    # We always calculate all three hashes for release assets, even when Oracle
    # only publishes one or two of them for a historical version.
    md5 = hash_file(zip_path, "md5")
    sha1 = hash_file(zip_path, "sha1")
    sha256 = hash_file(zip_path, "sha256")

    # Only compare algorithms Oracle actually published on the release page.
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
    # Individual files are convenient for aqua checksum config; the combined
    # file is a human-friendly release artifact.
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
    # Keep an unversioned alias for local POC scripts and manual inspection.
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


def _first_group(pattern: str | re.Pattern[str], text: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags) if isinstance(pattern, str) else pattern.search(text)
    if not match:
        return None
    return match.group(1) if match.lastindex else match.group(0)


def _page_text(soup: BeautifulSoup) -> str:
    source = soup.body or soup
    return source.get_text(separator=" ", strip=True)


def _version_from_page(text: str) -> str | None:
    return _first_group(VERSION_RE, text)


def _url_from_page(soup_context: BeautifulSoup, page_url: str) -> str | None:
    soup = soup_context.body or soup_context
    link = soup.find("a", href=ZIP_LINK_RE)
    if link is None:
        return None
    href = str(link.attrs["href"]).strip()
    url = urllib.parse.urljoin(page_url, href)

    return url


def _url_from_version(version_string: str) -> str:
    return VERSION_URL_TEMPLATE.format(version=version_string)


def _md5_from_page(text: str) -> str | None:
    checksum = _first_group(MD5_RE, text)
    return checksum.lower() if checksum else None


def _sha1_from_page(text: str) -> str | None:
    checksum = _first_group(SHA1_RE, text)
    return checksum.lower() if checksum else None


def _sha256_from_page(text: str) -> str | None:
    checksum = _first_group(SHA256_RE, text)
    return checksum.lower() if checksum else None


def _release_date_from_page(text: str) -> str | None:
    # dateparser handles Oracle's historical date formats, so this code does
    # not need per-page layout branches.
    dates = search_dates(text, settings=DATE_SEARCH_SETTINGS)
    if dates:
        return dates[0][1].date().isoformat()
    return None
