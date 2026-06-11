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

Install the Python dependencies before running the helper scripts locally:

```sh
python3 -m pip install -r requirements.txt
```

## Health checks

The `Health Check Oracle URLs` workflow lists this repository's releases and verifies that Oracle still serves:

```text
https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-{{VERSION}}.zip
```

The workflow is intentionally non-destructive. If Oracle removes a historical download, the workflow fails and reports the affected version. It does not delete releases, because deleting version metadata makes installs less predictable and erases useful checksum history.

## License and Oracle terms

This repository contains automation and metadata only. Oracle SQLcl is owned by Oracle and is subject to Oracle's license terms.
