#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import sys
import tempfile

from sqlcl_common import (
    DOWNLOAD_PAGE_URL,
    append_github_output,
    download_file,
    extract_version_from_zip,
    fetch_text,
    parse_download_page,
    verify_published_checksums,
    write_checksum_files,
    write_env_file,
    write_metadata,
    write_release_notes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover and validate the current Oracle SQLcl release.")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"), help="Directory for generated release assets.")
    parser.add_argument("--github-output", type=Path, help="Append version outputs for GitHub Actions.")
    parser.add_argument("--release-page", type=str, default=DOWNLOAD_PAGE_URL, help="URL to SQLcl version release page.")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {args.release_page}", file=sys.stderr)
    published = parse_download_page(fetch_text(args.release_page), page_url=args.release_page)

    with tempfile.TemporaryDirectory(prefix="sqlcl-release-") as tmp:
        temp_dir = Path(tmp)
        # Keep the downloaded zip out of release artifacts; only checksums and
        # metadata are written to --output-dir.
        zip_path = temp_dir / "sqlcl.zip"
        print(f"Downloading {published.url}", file=sys.stderr)
        download_file(published.url, zip_path)

        archive_version = extract_version_from_zip(zip_path)

        # The archive is the source of truth for the installed version. The page
        # must agree before we trust its checksums.
        # Some archive versions contain the short version, so check against that as well
        if archive_version != published.version and not published.version.startswith(archive_version + '.'):
            raise RuntimeError(
                "Downloaded archive version does not match Oracle download page: "
                f"archive={archive_version}, page={published.version}"
            )

        metadata = verify_published_checksums(zip_path, published, published.url, args.release_page)
        write_checksum_files(args.output_dir, metadata)
        write_release_notes(args.output_dir, metadata)
        write_metadata(args.output_dir, metadata)
        write_env_file(args.output_dir, metadata)

        if args.github_output:
            # GitHub Actions reads this file to drive release creation steps.
            append_github_output(
                args.github_output,
                [
                    ("version", metadata.version),
                    ("oracle_url", metadata.oracle_url),
                    ("md5", metadata.md5),
                    ("sha1", metadata.sha1),
                    ("sha256", metadata.sha256)
                ],
            )

        print(f"SQLcl {metadata.version}")
        print(f"Oracle URL: {metadata.oracle_url}")
        print(f"MD5: {metadata.md5}")
        print(f"SHA1: {metadata.sha1}")
        print(f"SHA256: {metadata.sha256}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
