#!/usr/bin/env python3
"""Rebuild list_items.csv and add new ingredients from the labels in ingredient_lists.csv.

Usage: python3 scripts/import_labels.py
Existing rows in ingredients.csv are kept as they are; new ingredients are appended.
"""
import csv
from pathlib import Path
from parse_label import items_from_label, normalize

data = Path(__file__).resolve().parent.parent / "data"
lists = list(csv.DictReader(open(data / "ingredient_lists.csv", encoding="utf-8")))
ing_path = data / "ingredients.csv"
ingredients = list(csv.DictReader(open(ing_path, encoding="utf-8")))
fields = list(ingredients[0].keys()) if ingredients else ["ingredient_id", "inci_name", "common_name", "cas", "ci_number", "functions", "synonyms", "cosing_url"]
known = {r["ingredient_id"] for r in ingredients}
# Map the database's earlier id for TiO2 onto the CI-keyed id.
alias_ids = {"ci-77891": "titanium-dioxide"} if "titanium-dioxide" in known else {}

rows = []
for lst in lists:
    pos = 0
    seen = set()
    for printed, may in items_from_label(lst["label_text"]):
        for iid, inci, common in normalize(printed):
            iid = alias_ids.get(iid, iid)
            if iid in seen:
                continue
            seen.add(iid)
            pos += 1
            rows.append({"list_id": lst["list_id"], "position": pos, "ingredient_id": iid,
                         "name_as_printed": printed, "may_contain": may})
            if iid not in known:
                known.add(iid)
                ci = iid[3:] if iid.startswith("ci-") else ""
                ingredients.append({"ingredient_id": iid, "inci_name": inci, "common_name": common, "cas": "",
                                    "ci_number": f"CI {ci}" if ci else "", "functions": "", "synonyms": "", "cosing_url": ""})

with open(data / "list_items.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["list_id", "position", "ingredient_id", "name_as_printed", "may_contain"])
    w.writeheader(); w.writerows(rows)
with open(ing_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader(); w.writerows(ingredients)
print(f"{len(lists)} labels -> {len(rows)} list items, {len(ingredients)} distinct ingredients")
