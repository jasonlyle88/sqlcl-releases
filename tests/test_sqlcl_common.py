from __future__ import annotations

import json
import zipfile

import pytest

from sqlcl_common import (
    PublishedDownload,
    ReleaseMetadata,
    extract_version_from_zip,
    parse_download_page,
    verify_published_checksums,
    write_checksum_files,
    write_env_file,
    write_metadata,
    write_release_notes,
)


def metadata() -> ReleaseMetadata:
    return ReleaseMetadata(
        version="26.1.2.132.1334",
        oracle_url="https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-26.1.2.132.1334.zip",
        oracle_release_asset_url="https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-26.1.2.132.1334.zip",
        oracle_release_page_url="https://www.oracle.com/database/sqldeveloper/technologies/sqlcl/download/",
        release_date="2026-05-12",
        md5="5d41402abc4b2a76b9719d911017c592",
        sha1="aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
        sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        oracle_published_md5="5d41402abc4b2a76b9719d911017c592",
        oracle_published_sha1="aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
        oracle_published_sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
    )


def test_parse_download_page_extracts_release_metadata() -> None:
    page = """
    <html>
      <body>
        <p>SQLcl 26.1.2.132.1334 was released May 12, 2026.</p>
        <a href="/otn_software/java/sqldeveloper/sqlcl-26.1.2.132.1334.zip">Download</a>
        <p>MD5: 5D41402ABC4B2A76B9719D911017C592</p>
        <p>SHA1: AAF4C61DDCC5E8A2DABEDE0F3B482CD9AEA9434D</p>
        <p>SHA256: 2CF24DBA5FB0A30E26E83B2AC5B9E29E1B161E5C1FA7425E73043362938B9824</p>
      </body>
    </html>
    """

    published = parse_download_page(page, page_url="https://download.oracle.com/sqlcl/download/")

    assert published == PublishedDownload(
        version="26.1.2.132.1334",
        url="https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-26.1.2.132.1334.zip",
        md5="5d41402abc4b2a76b9719d911017c592",
        sha1="aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
        sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        release_date="2026-05-12",
    )


def test_parse_download_page_falls_back_to_versioned_url() -> None:
    page = "<html><body><p>SQLcl 26.1.2.132.1334</p><p>MD5: 5d41402abc4b2a76b9719d911017c592</p></body></html>"

    published = parse_download_page(page, page_url="https://www.oracle.com/sqlcl/download/")

    assert published.url == "https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-26.1.2.132.1334.zip"


def test_parse_download_page_requires_version() -> None:
    with pytest.raises(RuntimeError, match="Could not find a SQLcl version"):
        parse_download_page("<html><body>No version here</body></html>", page_url="https://www.oracle.com/sqlcl/")


def test_extract_version_from_zip_prefers_version_file(tmp_path) -> None:
    zip_path = tmp_path / "sqlcl.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("sqlcl/bin/version.txt", "RELEASE=26.1.2.132.1334\n")
        archive.writestr("sqlcl/99.9.9.9.9", "")

    assert extract_version_from_zip(zip_path) == "26.1.2.132.1334"


def test_extract_version_from_zip_uses_unambiguous_marker_file(tmp_path) -> None:
    zip_path = tmp_path / "sqlcl.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("sqlcl/26.1.2.132.1334", "")

    assert extract_version_from_zip(zip_path) == "26.1.2.132.1334"


def test_extract_version_from_zip_rejects_ambiguous_marker_files(tmp_path) -> None:
    zip_path = tmp_path / "sqlcl.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("sqlcl/26.1.2.132.1334", "")
        archive.writestr("sqlcl/26.1.2.132.1335", "")

    with pytest.raises(RuntimeError, match="Could not determine SQLcl version"):
        extract_version_from_zip(zip_path)


def test_verify_published_checksums_returns_release_metadata(tmp_path) -> None:
    zip_path = tmp_path / "sqlcl.zip"
    zip_path.write_bytes(b"hello")
    published = PublishedDownload(
        version="26.1.2.132.1334",
        url="https://download.oracle.com/sqlcl.zip",
        md5="5d41402abc4b2a76b9719d911017c592",
        sha1="aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
        sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        release_date="2026-05-12",
    )

    result = verify_published_checksums(
        zip_path,
        published,
        asset_url="https://download.oracle.com/sqlcl.zip",
        page_url="https://www.oracle.com/sqlcl/download/",
    )

    assert result.version == "26.1.2.132.1334"
    assert result.md5 == published.md5
    assert result.sha1 == published.sha1
    assert result.sha256 == published.sha256


def test_verify_published_checksums_reports_mismatch(tmp_path) -> None:
    zip_path = tmp_path / "sqlcl.zip"
    zip_path.write_bytes(b"hello")
    published = PublishedDownload(
        version="26.1.2.132.1334",
        url="https://download.oracle.com/sqlcl.zip",
        md5="00000000000000000000000000000000",
        sha1=None,
        sha256=None,
        release_date=None,
    )

    with pytest.raises(RuntimeError, match="Oracle checksum verification failed"):
        verify_published_checksums(zip_path, published, asset_url=published.url, page_url="https://www.oracle.com/")


def test_verify_published_checksums_requires_published_checksum(tmp_path) -> None:
    zip_path = tmp_path / "sqlcl.zip"
    zip_path.write_bytes(b"hello")
    published = PublishedDownload(
        version="26.1.2.132.1334",
        url="https://download.oracle.com/sqlcl.zip",
        md5=None,
        sha1=None,
        sha256=None,
        release_date=None,
    )

    with pytest.raises(RuntimeError, match="did not publish any supported checksum"):
        verify_published_checksums(zip_path, published, asset_url=published.url, page_url="https://www.oracle.com/")


def test_write_release_artifacts(tmp_path) -> None:
    release_metadata = metadata()

    checksum_files = write_checksum_files(tmp_path, release_metadata)
    notes = write_release_notes(tmp_path, release_metadata)
    metadata_path = write_metadata(tmp_path, release_metadata)
    env_file = write_env_file(tmp_path, release_metadata)

    assert [path.name for path in checksum_files] == [
        "sqlcl-26.1.2.132.1334.zip.md5",
        "sqlcl-26.1.2.132.1334.zip.sha1",
        "sqlcl-26.1.2.132.1334.zip.sha256",
        "sqlcl-26.1.2.132.1334.checksums.txt",
    ]
    assert checksum_files[0].read_text(encoding="utf-8") == (
        "5d41402abc4b2a76b9719d911017c592  sqlcl-26.1.2.132.1334.zip\n"
    )
    assert "# SQLcl 26.1.2.132.1334\n" in notes.read_text(encoding="utf-8")
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["version"] == "26.1.2.132.1334"
    assert json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))["version"] == "26.1.2.132.1334"
    assert env_file.read_text(encoding="utf-8").startswith("VERSION=26.1.2.132.1334\n")
