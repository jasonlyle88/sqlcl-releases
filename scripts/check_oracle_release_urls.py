#!/usr/bin/env python3
"""Verify that Oracle still serves the SQLcl URLs for indexed GitHub releases."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlcl_common import USER_AGENT, request


def main() -> int:
    """Check every non-draft GitHub release against its metadata URL."""

    parser = argparse.ArgumentParser(description="Check whether Oracle still serves each indexed SQLcl release.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"), help="GitHub repository slug.")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token.")
    parser.add_argument("--github-summary", type=Path, help="GitHub step summary path.")
    args = parser.parse_args()

    if not args.repository:
        raise RuntimeError("--repository or GITHUB_REPOSITORY is required")

    releases = list_releases(args.repository, args.github_token)
    if not releases:
        print("No releases found.")
        return 0

    # rows: (release tag, metadata version, Oracle URL, status, detail)
    rows = []
    # failures: (release tag, metadata version, Oracle URL, failure detail)
    failures = []
    for release in releases:
        tag = release["tag_name"]
        try:
            metadata = fetch_release_metadata(release, args.github_token)
            version = metadata["version"]
            url = metadata["oracle_release_asset_url"]
        except (KeyError, RuntimeError, ValueError) as error:
            rows.append((tag, "", "", "metadata-error", str(error)))
            failures.append((tag, "", "", str(error)))
            continue

        ok, detail = oracle_url_exists(url)
        rows.append((tag, version, url, "ok" if ok else "unavailable", detail))
        if not ok:
            failures.append((tag, version, url, detail))

    report = render_report(rows)
    print(report)
    if args.github_summary:
        with args.github_summary.open("a", encoding="utf-8") as summary:
            summary.write(report)
            summary.write("\n")

    if failures:
        print("One or more Oracle release URLs are unavailable:", file=sys.stderr)
        for tag, version, url, detail in failures:
            print(f"- {tag}: {version} {url} ({detail})", file=sys.stderr)
        return 1
    return 0


def list_releases(repository: str, token: str | None) -> list[dict]:
    """Return all non-draft releases for a GitHub repository."""

    releases = []
    page = 1
    while True:
        # GitHub caps release listing at 100 items per page, so keep paging
        # until the API returns an empty page.
        url = f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}"
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with urllib.request.urlopen(request(url, headers=headers), timeout=60) as response:
            page_releases = json.loads(response.read().decode("utf-8"))
        if not page_releases:
            return releases
        releases.extend(release for release in page_releases if not release.get("draft"))
        page += 1


def fetch_release_metadata(release: dict, token: str | None) -> dict:
    """Download and parse the SQLcl metadata JSON asset from a GitHub release."""

    asset = find_metadata_asset(release)
    headers = {"Accept": "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with urllib.request.urlopen(request(asset["url"], headers=headers), timeout=60) as response:
        metadata = json.loads(response.read().decode("utf-8"))

    if not isinstance(metadata, dict):
        raise ValueError(f"{asset['name']} did not contain a JSON object")
    return metadata


def find_metadata_asset(release: dict) -> dict:
    """Return the release asset that contains the generated metadata JSON."""

    metadata_assets = [
        asset
        for asset in release.get("assets", [])
        if asset.get("name", "").endswith(".metadata.json")
    ]
    if len(metadata_assets) != 1:
        tag = release.get("tag_name", "<unknown>")
        raise RuntimeError(f"expected one metadata JSON asset for {tag}, found {len(metadata_assets)}")
    return metadata_assets[0]


def oracle_url_exists(url: str) -> tuple[bool, str]:
    """Check whether an Oracle archive URL is available without downloading it."""

    try:
        # HEAD is cheap and normally enough for Oracle's static downloads.
        with urllib.request.urlopen(request(url, method="HEAD"), timeout=30) as response:
            return 200 <= response.status < 400, f"HTTP {response.status}"
    except urllib.error.HTTPError as error:
        if error.code not in {403, 405}:
            return False, f"HTTP {error.code}"
    except urllib.error.URLError as error:
        return False, str(error.reason)

    try:
        # Some CDNs reject HEAD. A one-byte range request confirms availability
        # without downloading a full SQLcl archive.
        headers = {"Range": "bytes=0-0", "User-Agent": USER_AGENT}
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            return 200 <= response.status < 400, f"HTTP {response.status}"
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}"
    except urllib.error.URLError as error:
        return False, str(error.reason)


def render_report(rows: list[tuple[str, str, str, str, str]]) -> str:
    """Render health-check results as a Markdown table."""

    lines = [
        "# Oracle SQLcl URL health check",
        "",
        "| Release | Version | Status | Detail | Oracle URL |",
        "| --- | --- | --- | --- | --- |",
    ]
    for tag, version, url, status, detail in rows:
        escaped_url = urllib.parse.quote(url, safe=":/.-_")
        url_cell = f"<{escaped_url}>" if escaped_url else ""
        lines.append(f"| `{tag}` | `{version}` | {status} | {detail} | {url_cell} |")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
