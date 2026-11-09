"""Run: python3 tests/test_rate.py"""
import csv
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
fixture = root / "tests" / "fixture"
subprocess.run([sys.executable, str(root / "scripts" / "rate.py"), str(fixture)], check=True)
rows = {(r["ingredient_id"], r["route"]): r["rating"] for r in csv.DictReader(open(fixture / "assessments.csv"))}
assert rows[("titanium-dioxide", "inhalation")] == "Evidence of harm"
assert rows[("titanium-dioxide", "oral")] == "Unclear"
assert rows[("castor-oil", "oral")] == "No research found", "unreliable study must be ignored"
assert rows[("titanium-dioxide", "oral")] == "Unclear", "an approval must not override inconclusive evidence"
assert rows[("castor-oil", "dermal")] == "No concerns found", "a regulator approval for the route counts as no concerns"
assert rows[("linalool", "dermal")] == "Known allergen"
assert rows[("linalool", "inhalation")] == "No research found"
summary = {r["ingredient_id"]: r["worst_rating"] for r in csv.DictReader(open(fixture / "product_summaries.csv"))}
assert summary == {"castor-oil": "No research found", "linalool": "Known allergen", "titanium-dioxide": "Unclear"}, summary
print("all tests passed")
