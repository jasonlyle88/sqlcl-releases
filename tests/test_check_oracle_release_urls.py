"""Unit tests for GitHub release metadata selection and health report rendering."""

from __future__ import annotations

import pytest

from check_oracle_release_urls import find_metadata_asset, render_report


def test_find_metadata_asset_returns_single_metadata_asset() -> None:
    """Select the generated metadata JSON asset from the release asset list."""

    release = {
        "tag_name": "26.1.2.132.1334",
        "assets": [
            {"name": "sqlcl-26.1.2.132.1334.zip.sha256", "url": "https://api.github.com/sha256"},
            {"name": "sqlcl-26.1.2.132.1334.metadata.json", "url": "https://api.github.com/metadata"},
        ],
    }

    assert find_metadata_asset(release)["url"] == "https://api.github.com/metadata"


@pytest.mark.parametrize(
    ("assets", "expected_count"),
    [
        ([], 0),
        (
            [
                {"name": "sqlcl-26.1.2.132.1334.metadata.json"},
                {"name": "sqlcl-latest.metadata.json"},
            ],
            2,
        ),
    ],
)
def test_find_metadata_asset_requires_exactly_one_metadata_asset(assets, expected_count: int) -> None:
    """Fail when a release has no metadata asset or more than one candidate."""

    release = {"tag_name": "26.1.2.132.1334", "assets": assets}

    with pytest.raises(RuntimeError, match=f"found {expected_count}"):
        find_metadata_asset(release)


def test_render_report_outputs_markdown_table_with_escaped_url() -> None:
    """Render GitHub step-summary Markdown with a URL-safe Oracle download link."""

    report = render_report(
        [
            (
                "26.1.2.132.1334",
                "26.1.2.132.1334",
                "https://download.oracle.com/path with spaces/sqlcl-26.1.2.132.1334.zip",
                "ok",
                "HTTP 200",
            )
        ]
    )

    assert report == "\n".join(
        [
            "# Oracle SQLcl URL health check",
            "",
            "| Release | Version | Status | Detail | Oracle URL |",
            "| --- | --- | --- | --- | --- |",
            "| `26.1.2.132.1334` | `26.1.2.132.1334` | ok | HTTP 200 | "
            "<https://download.oracle.com/path%20with%20spaces/sqlcl-26.1.2.132.1334.zip> |",
        ]
    )
