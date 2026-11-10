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
# Several CI numbers in one item, written with slashes or bare numbers.
assert [i for i, _, _ in normalize("CI 77491/77492/77499 (Iron Oxides)")] == ["ci-77491", "ci-77492", "ci-77499"]
assert [i for i, _, _ in normalize("Iron Oxides (CI 77491, 77492, 77499)")] == ["ci-77491", "ci-77492", "ci-77499"]
# Latin duplicates after a slash, footnote stars, and "Polyglyceryl-3 Beeswax" is not beeswax.
assert normalize("Helianthus Annuus (Sunflower) Seed Wax/Helianthus Annuus Seed Cera")[0][0] == "helianthus-annuus-sunflower-seed-wax"
assert normalize("POLYGLYCERYL-3 BEESWAX")[0][0] == "polyglyceryl-3-beeswax"
assert normalize("Hordeum Distichon (barley) Extract Extrait D'orge À Deux Rangs")[0][0] == "hordeum-distichon-barley-extract"
for label in ["A, B. +/- (May Contain) Mica, Titanium Dioxide (CI 77891).",
              "A, B [May Contain: Mica, Titanium Dioxide (CI 77891)]",
              "A, B, [+/ -: Mica, Ci 77891]",
              "A, B. May Contain/Peut Contenir: (+/-) Mica, CI 77891 (Titanium Dioxide).",
              "A, B* [+/- MAY CONTAIN / PEUT CONTENIR, MICA, CI 77891/TITANIUM DIOXIDE]"]:
    got = items_from_label(label)
    assert [n for n, _ in got][:2] == ["A", "B"] and [m for _, m in got] == ["no", "no", "yes", "yes"], (label, got)
# Sunscreen Drug Facts labels: actives first, with their strength.
from parse_label import label_sections, strip_strength
parts = label_sections("Active Ingredients: Avobenzone 3%, Homosalate (10%). Inactive Ingredients: Castor Oil, Flavor.")
assert parts == [("Avobenzone 3%, Homosalate (10%)", True), ("Castor Oil, Flavor", False)], parts
assert label_sections("A, B")[0] == ("A, B", False)
assert label_sections("Active Ingredients (Sunscreen): Zinc Oxide 3.0%. Inactive Ingredients: A")[0] == ("Zinc Oxide 3.0%", True)
assert strip_strength("22% Transparent Zinc Oxide") == "Transparent Zinc Oxide"
assert strip_strength("Zinc Oxide 10% (Sunscreen)") == "Zinc Oxide"
assert normalize(strip_strength("22% Transparent Zinc Oxide"))[0][0] == "ci-77947"
assert normalize("white petrolatum")[0][0] == "petrolatum"
assert normalize("Red 28 Lake")[0][0] == "ci-45410" and normalize("Yellow 5 Lake")[0][0] == "ci-19140"
assert normalize("Cocos Nucifera (Coconut) Oil (ORGANIC)")[0][0] == "cocos-nucifera-coconut-oil"
assert [n for n, _ in items_from_label("Behenyl Behenate,Butyloctyl Salicylate Calcium Sodium Borosilicate, Diethylhexyl 2,6-Naphthalate")] == [
    "Behenyl Behenate", "Butyloctyl Salicylate", "Calcium Sodium Borosilicate", "Diethylhexyl 2,6-Naphthalate"]
print("all tests passed")
