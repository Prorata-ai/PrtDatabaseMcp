#!/usr/bin/env python3
"""Build catalog/generated.json from Prisma schema and SQLAlchemy model hints."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_OUT = ROOT / "catalog" / "generated.json"
PRISMA_SCHEMA = ROOT.parent / "PrtPublisherPortal" / "prisma" / "schema.prisma"
INFERENCE_MODELS = ROOT.parent / "PrtDocumentInference" / "src" / "prtdocumentinference" / "models"


def parse_prisma_models(text: str) -> dict:
    tables = {}
    model_re = re.compile(
        r"model\s+(\w+)\s*\{([^}]*)\}",
        re.MULTILINE | re.DOTALL,
    )
    map_re = re.compile(r"@@map\(\"([^\"]+)\"\)")
    for match in model_re.finditer(text):
        model_name = match.group(1)
        body = match.group(2)
        table = model_name
        map_match = map_re.search(body)
        if map_match:
            table = map_match.group(1)
        columns = {}
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("@@"):
                continue
            if "@" in line.split()[0] if line.split() else "":
                continue
            parts = line.split()
            if len(parts) >= 2:
                columns[parts[0]] = parts[1]
        tables[table] = {
            "service": "PrtPublisherPortal",
            "schema": "public",
            "prismaModel": model_name,
            "columns": columns,
        }
    return tables


def parse_inference_tablenames() -> dict:
    tables = {}
    if not INFERENCE_MODELS.is_dir():
        return tables
    tablename_re = re.compile(r'__tablename__\s*=\s*["\']([^"\']+)["\']')
    for path in INFERENCE_MODELS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in tablename_re.findall(text):
            tables[name] = {
                "service": "PrtDocumentInference",
                "schema": "public",
                "sourceFile": str(path.relative_to(ROOT.parent)),
                "columns": {},
            }
    return tables


def main() -> int:
    tables: dict = {}

    if PRISMA_SCHEMA.is_file():
        tables.update(parse_prisma_models(PRISMA_SCHEMA.read_text(encoding="utf-8")))
        print(f"Prisma: {len(tables)} tables from {PRISMA_SCHEMA}")
    else:
        print(f"Warning: Prisma schema not found at {PRISMA_SCHEMA}", file=sys.stderr)

    inference = parse_inference_tablenames()
    for name, meta in inference.items():
        if name not in tables:
            tables[name] = meta
        else:
            tables[name]["alsoUsedBy"] = "PrtDocumentInference"
    print(f"Inference: {len(inference)} tables")

    structured = {
        "product": {
            "service": "PrtIndexingIngest",
            "schema": "catalog",
            "description": "schema.org Product (PrtSchemas catalog_v1)",
            "columns": {},
        },
        "event": {
            "service": "PrtIndexingIngest",
            "schema": "catalog",
            "description": "schema.org Event (PrtSchemas catalog_v1)",
            "columns": {},
        },
        "place": {
            "service": "PrtIndexingIngest",
            "schema": "catalog",
            "description": "schema.org Place (PrtSchemas catalog_v1)",
            "columns": {},
        },
        "offer": {
            "service": "PrtIndexingIngest",
            "schema": "catalog",
            "description": "schema.org Offer variants for catalog.product",
            "columns": {},
        },
    }
    for name, meta in structured.items():
        tables.setdefault(name, meta)

    CATALOG_OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "tables": tables,
    }
    CATALOG_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {CATALOG_OUT} ({len(tables)} tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
