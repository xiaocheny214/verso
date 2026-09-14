"""Export the FastAPI schema as a deterministic JSON contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from verso_app.bootstrap.app import app


def render_schema() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed schema differs from the FastAPI application.",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    rendered = render_schema()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != rendered:
            print(f"OpenAPI schema is stale: {output}", file=sys.stderr)
            return 1
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"Exported OpenAPI schema to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
