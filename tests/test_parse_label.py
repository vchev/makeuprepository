"""Run: python3 tests/test_parse_label.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from parse_label import items_from_label, normalize

items = items_from_label("Ricinus Communis (Castor) Seed Oil, Cera Alba/Beeswax/Cire d'abeille, Tocopherol. "
                         "May Contain/Peut Contenir (±): CI 77491, CI 77492 (Iron Oxides), CI 77891 (Titanium Dioxide).")
assert [m for _, m in items] == ["no", "no", "no", "yes", "yes", "yes"], items
ids = [i for name, _ in items for i, _, _ in normalize(name)]
assert ids == ["ricinus-communis-castor-seed-oil", "beeswax", "tocopherol", "ci-77491", "ci-77492", "ci-77891"], ids
assert normalize("Iron Oxides (CI 77491, CI 77492)") == [("ci-77491", "CI 77491", "Iron oxides (red)"), ("ci-77492", "CI 77492", "Iron oxides (yellow)")]
assert normalize("Cera Alba/Beeswax/Cire d'abeille")[0][0] == "beeswax"
assert normalize("Synthetic Beeswax")[0][0] == "synthetic-beeswax"
assert normalize("Euphorbia Cerifera (candelilla) Wax Candelilla Cera Cire De Candelilla")[0][0] == "euphorbia-cerifera-candelilla-wax"
assert normalize("PARFUM (FRAGRANCE)")[0][0] == "fragrance"
dior = items_from_label("A • B (C, D) • [+/- CI 77891 (TITANIUM DIOXIDE) • CI 15850 (RED 7)]")
assert dior == [("A", "no"), ("B (C, D)", "no"), ("CI 77891 (TITANIUM DIOXIDE)", "yes"), ("CI 15850 (RED 7)", "yes")], dior
print("all tests passed")
