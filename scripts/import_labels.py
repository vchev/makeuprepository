#!/usr/bin/env python3
"""Rebuild list_items.csv and add new ingredients from the labels in ingredient_lists.csv.

Usage: python3 scripts/import_labels.py
Existing rows in ingredients.csv are kept as they are; new ingredients are appended.
"""
import csv
import re
from pathlib import Path
from parse_label import items_from_label, label_sections, normalize, strip_strength

data = Path(__file__).resolve().parent.parent / "data"
lists = list(csv.DictReader(open(data / "ingredient_lists.csv", encoding="utf-8")))
ing_path = data / "ingredients.csv"
ingredients = list(csv.DictReader(open(ing_path, encoding="utf-8")))
fields = list(ingredients[0].keys()) if ingredients else ["ingredient_id", "inci_name", "common_name", "cas", "ci_number", "functions", "synonyms", "cosing_url"]
known = {r["ingredient_id"] for r in ingredients}


def plain_key(inci):
    """INCI name without parenthesised common names: "Passiflora Edulis (Passion Fruit) Seed Oil" == "Passiflora Edulis Seed Oil"."""
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"\s*\([^)]*\)", "", inci.lower())).strip("-")


by_plain = {}
for r in ingredients:
    if not r["ingredient_id"].startswith("ci-"):
        by_plain.setdefault(plain_key(r["inci_name"]), r["ingredient_id"])
# Map the database's earlier id for TiO2 onto the CI-keyed id.
alias_ids = {"ci-77891": "titanium-dioxide"} if "titanium-dioxide" in known else {}

rows = []
for lst in lists:
    pos = 0
    seen = set()
    items = [(printed, may, active) for text, active in label_sections(lst["label_text"])
             for printed, may in items_from_label(text)]
    for printed, may, active in items:
        for iid, inci, common in normalize(strip_strength(printed) if active else printed):
            iid = alias_ids.get(iid, iid)
            if iid not in known and not iid.startswith("ci-"):
                iid = by_plain.get(plain_key(inci), iid)
            if iid in seen:
                continue
            seen.add(iid)
            pos += 1
            rows.append({"list_id": lst["list_id"], "position": pos, "ingredient_id": iid,
                         "name_as_printed": printed, "may_contain": may,
                         "active": "yes" if active else "no"})
            if iid not in known:
                known.add(iid)
                by_plain.setdefault(plain_key(inci), iid)
                ci = iid[3:] if iid.startswith("ci-") else ""
                ingredients.append({"ingredient_id": iid, "inci_name": inci, "common_name": common, "cas": "",
                                    "ci_number": f"CI {ci}" if ci else "", "functions": "", "synonyms": "", "cosing_url": ""})

with open(data / "list_items.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["list_id", "position", "ingredient_id", "name_as_printed", "may_contain", "active"])
    w.writeheader(); w.writerows(rows)
with open(ing_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader(); w.writerows(ingredients)
print(f"{len(lists)} labels -> {len(rows)} list items, {len(ingredients)} distinct ingredients")
