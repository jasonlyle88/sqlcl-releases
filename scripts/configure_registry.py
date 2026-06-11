#!/usr/bin/env python3
"""Configure registry.yaml for a target GitHub owner/repository."""

from __future__ import annotations

from pathlib import Path
import argparse
import re


def main() -> int:
    """Rewrite the registry package owner and repository references."""

    parser = argparse.ArgumentParser(description="Set repo_owner and repo_name in registry.yaml.")
    parser.add_argument("--owner", required=True, help="GitHub owner or organization.")
    parser.add_argument("--repo", required=True, help="GitHub repository name.")
    parser.add_argument("--registry", type=Path, default=Path("registry.yaml"))
    args = parser.parse_args()

    text = args.registry.read_text(encoding="utf-8")
    # The registry contains a single package entry, so only the first owner/repo
    # pair should be rewritten.
    text = re.sub(r"(\n\s*repo_owner:\s*)\S+", rf"\g<1>{args.owner}", text, count=1)
    text = re.sub(r"(\n\s*repo_name:\s*)\S+", rf"\g<1>{args.repo}", text, count=1)
    text = text.replace("github.com/jlyle/sqlcl-aqua-registry", f"github.com/{args.owner}/{args.repo}")
    args.registry.write_text(text, encoding="utf-8")
    print(f"Updated {args.registry} for {args.owner}/{args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
