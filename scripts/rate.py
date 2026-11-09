#!/usr/bin/env python3
"""Validate the database CSVs and compute ingredient ratings automatically.

Usage: python3 scripts/rate.py [data_dir]
Writes <data_dir>/assessments.csv and <data_dir>/product_summaries.csv.
Rules are applied in order; the first match wins (see README "Rating rules").
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

TABLES = ["brands", "products", "ingredient_lists", "list_items", "ingredients", "sources",
          "findings", "regulatory_status", "category_routes"]
ROUTES = ["oral", "dermal", "inhalation", "eye"]
RATINGS = ["Evidence of harm", "Known allergen", "Unclear", "No concerns found", "No research found"]
# For a product's summary, a route with no research counts as worse than a route with no
# concerns, so a gap in the evidence is never shown as "No concerns found".
SUMMARY_ORDER = ["Evidence of harm", "Known allergen", "Unclear", "No research found", "No concerns found"]
HUMAN = {"human_population", "human_clinical"}
ASSESSMENTS = {"regulatory_assessment", "expert_panel_assessment"}


def load(data_dir):
    db = {}
    for t in TABLES:
        with open(data_dir / f"{t}.csv", newline="", encoding="utf-8") as f:
            db[t] = list(csv.DictReader(f))
    return db


def validate(db, schema):
    errors = []
    for key, allowed in schema["allowed"].items():
        table, col = key.split(".")
        for i, row in enumerate(db[table], start=2):
            if row.get(col, "") not in allowed:
                errors.append(f"{table}.csv line {i}: {col}={row.get(col)!r} not in {allowed}")
    for key, target in schema["references"].items():
        table, col = key.split(".")
        ttable, tcol = target.split(".")
        valid = {r[tcol] for r in db[ttable]}
        for i, row in enumerate(db[table], start=2):
            if row[col] and row[col] not in valid:
                errors.append(f"{table}.csv line {i}: {col}={row[col]!r} has no match in {ttable}.{tcol}")
    return errors


def usable(f, sources):
    """Quality gate: only reliable, fully read evidence can move a rating.

    Studies must be peer-reviewed and scored Klimisch 1 or 2 (reliable without or with
    restrictions). Regulatory opinions, expert panel reports and IARC classifications are
    'authoritative'. Every finding must come from the full text: an abstract or summary
    is not enough. The one exception is an IARC classification, where the official
    classification itself is the finding. Everything else stays on record but is ignored.
    """
    read = f["what_was_read"]
    if read != "full_text":
        if not (read == "classification_only" and sources[f["source_id"]]["source_type"] == "iarc_monograph"):
            return False
    if f["reliability"] == "authoritative":
        return True
    return f["peer_reviewed"] == "yes" and f["reliability"] in ("1", "2")


def route_matches(row_route, route):
    return row_route in (route, "all")


def rate(ingredient_id, route, findings, regs, sources):
    """Return (rating, reason, [source_ids]) for one ingredient and route."""
    findings = [f for f in findings if usable(f, sources)]
    f_here = [f for f in findings if f["route"] == route]
    f_lab = [f for f in findings if f["route"] == "lab_only"]
    r_here = [r for r in regs if route_matches(r["route"], route)]

    # Rule 1: Evidence of harm
    for r in r_here:
        if r["status"] in ("banned", "restricted") and r["reason"] == "safety":
            return RATINGS[0], f"{r['status'].capitalize()} for safety in {r['jurisdiction']}", [r["source_id"]]
    for f in f_here:
        if f["endpoint"] == "skin_allergy" or f["result"] != "harm":
            continue
        group = sources[f["source_id"]]["iarc_group"]
        if group in ("1", "2A"):
            return RATINGS[0], f"IARC Group {group} by {route}", [f["source_id"]]
        if f["study_type"] in ASSESSMENTS and f["dose_relevance"] == "cosmetic_level":
            return RATINGS[0], "Regulatory or expert panel assessment found harm at cosmetic levels", [f["source_id"]]
        if f["study_type"] in HUMAN and f["dose_relevance"] == "cosmetic_level":
            return RATINGS[0], "Human study found harm at cosmetic-level exposure", [f["source_id"]]

    # Rule 2: Known allergen (contact routes only)
    if route != "inhalation":
        for r in regs:
            if r["status"] == "allergen_listed":
                return RATINGS[1], f"Listed as a cosmetic allergen ({r['jurisdiction']})", [r["source_id"]]
        for f in findings:
            if f["endpoint"] == "skin_allergy" and f["result"] == "harm" and f["study_type"] in HUMAN:
                return RATINGS[1], "Allergy reported in human patch-test or clinical studies", [f["source_id"]]

    # Rule 3: Unclear
    mixed = [f for f in f_here + f_lab if f["result"] in ("harm", "inconclusive")]
    if mixed:
        return (RATINGS[2], "Harm reported only in limited, high-dose or inconclusive evidence",
                sorted({f["source_id"] for f in mixed}))

    # Rule 4: No concerns found
    clear = [f for f in f_here if f["result"] == "no_harm"]
    if clear:
        return RATINGS[3], "Studies or assessments found no harm", sorted({f["source_id"] for f in clear})
    approved = [r for r in r_here if r["status"] == "allowed"]
    if approved:
        return (RATINGS[3], "Approved for this use by a regulator (" +
                ", ".join(sorted({r["jurisdiction"] for r in approved})) + ")",
                sorted({r["source_id"] for r in approved}))

    # Rule 5: No research found
    return RATINGS[4], "No relevant studies or regulatory opinions found for this route", []


def main():
    data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data")
    schema = json.loads((Path(__file__).resolve().parent.parent / "data" / "schema.json").read_text())
    db = load(data_dir)
    errors = validate(db, schema)
    if errors:
        print("Validation failed:", *errors, sep="\n  ")
        sys.exit(1)

    sources = {s["source_id"]: s for s in db["sources"]}
    findings = defaultdict(list)
    for f in db["findings"]:
        findings[f["ingredient_id"]].append(f)
    regs = defaultdict(list)
    for r in db["regulatory_status"]:
        regs[r["ingredient_id"]].append(r)

    today = date.today().isoformat()
    ratings = {}
    with open(data_dir / "assessments.csv", "w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["ingredient_id", "route", "rating", "reason", "source_ids", "rated_on"])
        for ing in db["ingredients"]:
            for route in ROUTES:
                rating, reason, srcs = rate(ing["ingredient_id"], route, findings[ing["ingredient_id"]],
                                            regs[ing["ingredient_id"]], sources)
                ratings[(ing["ingredient_id"], route)] = rating
                w.writerow([ing["ingredient_id"], route, rating, reason, ";".join(srcs), today])

    routes_for = defaultdict(list)
    for cr in db["category_routes"]:
        routes_for[cr["category"]].append(cr["route"])
    items_for = defaultdict(list)
    for li in db["list_items"]:
        items_for[li["list_id"]].append(li)
    product = {p["product_id"]: p for p in db["products"]}

    with open(data_dir / "product_summaries.csv", "w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["list_id", "product_id", "shade", "ingredient_id", "worst_rating", "rating_by_route"])
        for lst in db["ingredient_lists"]:
            routes = routes_for[product[lst["product_id"]]["category"]]
            for li in sorted(items_for[lst["list_id"]], key=lambda x: int(x["position"])):
                by_route = {r: ratings[(li["ingredient_id"], r)] for r in routes}
                worst = min(by_route.values(), key=SUMMARY_ORDER.index)
                w.writerow([lst["list_id"], lst["product_id"], lst["shade"], li["ingredient_id"], worst,
                            "; ".join(f"{r}: {v}" for r, v in by_route.items())])

    counts = Counter(ratings.values())
    print(f"OK: {len(db['ingredients'])} ingredients rated across {len(ROUTES)} routes. " +
          ", ".join(f"{k}: {counts[k]}" for k in RATINGS if counts[k]))


if __name__ == "__main__":
    main()
