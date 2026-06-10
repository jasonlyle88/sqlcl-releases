#!/usr/bin/env python3
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import threading


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated local mise/aqua SQLcl proof of concept.")
    parser.add_argument("--metadata", type=Path, default=Path("dist/metadata.json"))
    parser.add_argument("--work-dir", type=Path, default=Path("work/local-poc"))
    args = parser.parse_args()

    metadata_path = resolve_metadata_path(args.metadata)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    version = metadata["version"]
    sha256 = metadata["sha256"]

    mise = shutil.which("mise")
    if not mise:
        raise RuntimeError("mise was not found on PATH")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"sqlcl-{version}.zip"
    checksum_name = f"{archive_name}.sha256"
    # The POC serves only the checksum file locally. The SQLcl zip still comes
    # directly from Oracle, matching the real registry behavior.
    (args.work_dir / checksum_name).write_text(f"{sha256}  {archive_name}\n", encoding="utf-8")

    # Use an ephemeral localhost port so the helper does not conflict with
    # anything already running on the machine.
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(SimpleHTTPRequestHandler, directory=str(args.work_dir)),
    )
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # This temporary registry mirrors the production package entry but points
    # checksum lookup at the local HTTP server.
    registry = args.work_dir / "registry.yaml"
    registry.write_text(
        f"""# yaml-language-server: $schema=https://raw.githubusercontent.com/aquaproj/aqua/main/json-schema/registry.json
packages:
  - type: http
    name: oracle.com/sqlcl
    repo_owner: local
    repo_name: sqlcl-aqua-registry
    url: https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-{{{{.Version}}}}.zip
    format: zip
    files:
      - name: sql
        src: sqlcl/bin/sql
    checksum:
      type: http
      url: http://127.0.0.1:{port}/sqlcl-{{{{.Version}}}}.zip.sha256
      file_format: raw
      algorithm: sha256
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    # Keep mise cache/config/data isolated from the user's normal environment.
    env.update(
        {
            "MISE_AQUA_REGISTRIES": f"file://{args.work_dir.resolve()}",
            "MISE_AQUA_BAKED_REGISTRY": "false",
            "MISE_CACHE_DIR": str((Path("work") / "mise-cache").resolve()),
            "MISE_CONFIG_DIR": str((Path("work") / "mise-config").resolve()),
            "MISE_DATA_DIR": str((Path("work") / "mise-data").resolve()),
            "MISE_YES": "1",
        }
    )

    try:
        subprocess.run([mise, "install", f"aqua:oracle.com/sqlcl@{version}"], check=True, env=env)
        subprocess.run([mise, "where", f"aqua:oracle.com/sqlcl@{version}"], check=True, env=env)
    finally:
        server.shutdown()
        server.server_close()
    return 0


def resolve_metadata_path(path: Path) -> Path:
    if path.exists():
        return path
    candidates = sorted(path.parent.glob("sqlcl-*.metadata.json"))
    if candidates:
        return candidates[-1]
    raise FileNotFoundError(f"Metadata file not found: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
