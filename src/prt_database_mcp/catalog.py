"""Schema catalog loaded from generated.json + domain docs."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


DOMAIN_DOCS: Dict[str, str] = {
    "publishers": (
        "PrtPublisherPortal: publisher accounts. Join publisher_groups, sites, channels."
    ),
    "sites": "PrtPublisherPortal: crawl targets per publisher (URLs, config).",
    "inference_requests": (
        "PrtDocumentInference: document processing requests (status, document_id, publisher_id)."
    ),
    "batch_jobs": "PrtDocumentInference: Gemini batch job tracking.",
    "batch_documents": "PrtDocumentInference: documents assigned to a batch job.",
    "structured_products": "PrtIndexingIngest: schema.org Product rows for structured RAG.",
}


def load_catalog(path: Optional[str]) -> Dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {"tables": {}, "source": "none"}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("tables", {})
    return data


def search_catalog(catalog: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []

    tables: Dict[str, Any] = catalog.get("tables") or {}
    hits: List[Dict[str, Any]] = []

    for table_name, meta in tables.items():
        score = 0
        service = (meta.get("service") or "").lower()
        desc = (meta.get("description") or DOMAIN_DOCS.get(table_name, "")).lower()
        if q in table_name.lower():
            score += 3
        if q in service:
            score += 2
        if q in desc:
            score += 1
        for col in (meta.get("columns") or {}):
            if q in col.lower():
                score += 1
        if score > 0:
            hits.append(
                {
                    "table": table_name,
                    "schema": meta.get("schema", "public"),
                    "service": meta.get("service"),
                    "description": meta.get("description") or DOMAIN_DOCS.get(table_name),
                    "score": score,
                }
            )

    for table_name, doc in DOMAIN_DOCS.items():
        if table_name in tables:
            continue
        if q in table_name or q in doc.lower():
            hits.append(
                {
                    "table": table_name,
                    "schema": "public",
                    "service": None,
                    "description": doc,
                    "score": 1,
                }
            )

    hits.sort(key=lambda h: (-h["score"], h["table"]))
    return hits[:25]


def catalog_markdown(catalog: Dict[str, Any]) -> str:
    tables: Dict[str, Any] = catalog.get("tables") or {}
    lines = ["# ProRata database catalog", ""]
    if not tables:
        lines.append("_No generated catalog. Run `python scripts/build_catalog.py`._")
        lines.append("")
        for name, doc in sorted(DOMAIN_DOCS.items()):
            lines.append(f"- **{name}**: {doc}")
        return "\n".join(lines)

    by_service: Dict[str, List[str]] = {}
    for table_name, meta in sorted(tables.items()):
        svc = meta.get("service") or "unknown"
        by_service.setdefault(svc, []).append(table_name)

    for svc, names in sorted(by_service.items()):
        lines.append(f"## {svc}")
        for name in names:
            meta = tables[name]
            desc = meta.get("description") or DOMAIN_DOCS.get(name, "")
            lines.append(f"- `{name}` ({meta.get('schema', 'public')}): {desc}")
        lines.append("")
    return "\n".join(lines)
