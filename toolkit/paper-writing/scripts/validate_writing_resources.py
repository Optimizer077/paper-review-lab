#!/usr/bin/env python3
"""Validate the support catalog's structure, identity and disclosed scope.

This offline check does not authenticate sources or verify editorial judgments.
"""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

CATEGORIES = {
    "planning-argument": "Planning and argument",
    "structure-sections": "Paper structure and sections",
    "clarity-language": "Clarity and academic language",
    "methods-reporting": "Methods and reporting",
    "figures-tables": "Figures and tables",
    "citations-integrity": "Citations, authorship and integrity",
    "review-submission": "Review and submission",
    "tools-workflow": "Tools and writing workflow",
}
TYPES = {"guide", "course", "book", "reporting-guideline", "documentation", "tool"}
ACCESS = {"open-web", "mixed", "book-or-library", "institutional-or-paid", "open-source"}
LEVELS = {"page-content", "publisher-metadata", "author-metadata", "source-code-documentation", "indexed-primary-excerpt"}
PROFILES = {"empirical-ml", "theory", "clinical", "systematic-review"}
FIELDS = {"id", "title", "provider", "url", "category", "resource_type", "tasks", "profiles",
          "summary", "how_to_use", "limits", "access", "inspection_level", "verified_at",
          "verification_url", "source_note", "primary_source", "tags"}


def source_url(value):
    if not isinstance(value, str):
        raise ValueError("Source URL must be text")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Source URL must be HTTPS without embedded credentials")
    return urlunsplit((parsed.scheme, parsed.netloc.casefold(), parsed.path.rstrip("/"), parsed.query, ""))


def validate(data):
    required = {"version", "title", "updated_at", "selection_policy", "scope", "categories", "starter_ids", "resources"}
    if not isinstance(data, dict) or set(data) != required or type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("Unsupported support-catalog schema")
    if data["categories"] != CATEGORIES or not isinstance(data["resources"], list) or not data["resources"]:
        raise ValueError("Catalog needs the declared categories and resources")
    if not isinstance(data["updated_at"], str):
        raise ValueError("Catalog update date must be ISO date text")
    updated = date.fromisoformat(data["updated_at"])
    for name in ("title", "selection_policy", "scope"):
        if not isinstance(data[name], str) or not data[name].strip():
            raise ValueError(f"Catalog needs {name}")
    ids, urls = set(), set()
    for row in data["resources"]:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("Each support resource needs exactly the documented fields")
        if not isinstance(row["id"], str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", row["id"]) or row["id"] in ids:
            raise ValueError("Resource IDs must be unique slugs")
        ids.add(row["id"])
        key = source_url(row["url"])
        source_url(row["verification_url"])
        if key in urls:
            raise ValueError("Duplicate primary resource URL")
        urls.add(key)
        if not all(isinstance(row[field], str) for field in ("category", "resource_type", "access", "inspection_level")):
            raise ValueError("Resource classifications must be text")
        if row["category"] not in CATEGORIES or row["resource_type"] not in TYPES or row["access"] not in ACCESS:
            raise ValueError("Unknown resource classification")
        if row["inspection_level"] not in LEVELS or row["primary_source"] is not True:
            raise ValueError("Disclose a supported primary-source inspection level")
        if not isinstance(row["verified_at"], str):
            raise ValueError("Verification date must be ISO date text")
        verified = date.fromisoformat(row["verified_at"])
        if verified > date.today() or verified > updated:
            raise ValueError("Verification cannot be dated in the future")
        for field in ("title", "provider", "summary", "how_to_use", "limits", "source_note"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"Resource needs nonempty {field}")
        for field, limit in (("summary", 40), ("how_to_use", 40), ("limits", 50)):
            if len(row[field].split()) > limit:
                raise ValueError(f"{row['id']} {field} exceeds its editorial length limit")
        for field in ("tasks", "tags", "profiles"):
            values = row[field]
            if not isinstance(values, list) or not values or not all(isinstance(s, str) and s.strip() for s in values):
                raise ValueError(f"Resource needs a nonempty {field} list")
            if len(set(values)) != len(values):
                raise ValueError(f"Duplicate entries in {field}")
        if not set(row["profiles"]).issubset(PROFILES):
            raise ValueError("Unknown contribution profile")
    starters = data["starter_ids"]
    if not isinstance(starters, list) or not all(isinstance(s, str) for s in starters) or len(set(starters)) != len(starters) or not set(starters).issubset(ids):
        raise ValueError("Starting points must be distinct IDs in the catalog")
    return {"resources": len(ids), "categories": dict(sorted(Counter(r["category"] for r in data["resources"]).items())),
            "inspection_levels": dict(sorted(Counter(r["inspection_level"] for r in data["resources"]).items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    data = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    print(json.dumps({"status": "valid", **validate(data)}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f"Invalid support catalog: {error}")
