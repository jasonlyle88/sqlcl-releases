# SQLcl Releases registry

This repository is a metadata-only release registry for Oracle SQLcl.

It is intended for use with the [aqua CLI Version Manager](https://aquaproj.github.io/)/[mise](https://mise.jdx.dev/), but can be used for any discovery purpose.

It does not mirror or redistribute Oracle SQLcl zip archives. Installs via aqua/mise still download SQLcl directly from Oracle:

```text
https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-{{.Version}}.zip
```

GitHub releases in this repository are used as an index for version discovery and as a home for checksum files generated from Oracle's current download.

## Why this exists

The upstream aqua registry currently installs SQLcl as an `http` package. That is the right package type for Oracle-hosted downloads, but the package needs GitHub release metadata to make version discovery work well in mise.

This repo keeps those concerns separate:

- GitHub releases in this repo provide version discovery.
- Checksum-only release assets provide aqua/mise checksum verification.
- SQLcl itself is downloaded from Oracle, not from this repo.

## Local development

Install the locked Python environment before running the helper scripts locally:

```sh
uv sync
```

Run helper scripts through uv so they use the project environment:

```sh
uv run scripts/discover_sqlcl_release.py --help
uv run scripts/discover_sqlcl_release.py --output-dir dist --github-output temp/sqlcl.$(date +%s)
uv run scripts/check_oracle_release_urls.py --help
uv run scripts/check_oracle_release_urls.py --repository "$(gh repo view --json nameWithOwner -q .nameWithOwner)" --github-token "$(gh auth token)"
```

Run the local quality checks before opening a pull request:

```sh
uv sync --all-groups
uv run ruff format --check scripts tests
uv run ruff check scripts tests
uv run pytest
```

The pytest suite is intentionally local-only by default. Tests that call Oracle or GitHub should be marked
`@pytest.mark.network` so they can be run explicitly when needed.

## Health checks

The `Health Check Oracle URLs` workflow lists this repository's releases, reads each release's metadata JSON asset, and verifies that Oracle still serves the recorded `oracle_release_asset_url`.

The workflow is intentionally non-destructive. If Oracle removes a historical download, the workflow fails and reports the affected version. It does not delete releases, because deleting version metadata makes installs less predictable and erases useful checksum history.

## License and Oracle terms

This repository contains automation and metadata only. Oracle SQLcl is owned by Oracle and is subject to Oracle's license terms.
