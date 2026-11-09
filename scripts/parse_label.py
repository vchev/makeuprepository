#!/usr/bin/env python3
"""Split a printed ingredient label into items and map each to a standard ingredient id.

Used by scripts/import_labels.py. Colorants are keyed by their CI number, so
"Red 7 Lake (CI 15850)" and "CI 15850 (Red 6)" become the same ingredient, as in EU CosIng.
"""
import re

COLORANTS = {
    "77891": ("ci-77891", "TITANIUM DIOXIDE", "Titanium dioxide"),
    "77491": ("ci-77491", "CI 77491", "Iron oxides (red)"),
    "77492": ("ci-77492", "CI 77492", "Iron oxides (yellow)"),
    "77499": ("ci-77499", "CI 77499", "Iron oxides (black)"),
    "77742": ("ci-77742", "MANGANESE VIOLET", "Manganese violet"),
    "77163": ("ci-77163", "BISMUTH OXYCHLORIDE", "Bismuth oxychloride"),
    "77510": ("ci-77510", "FERRIC FERROCYANIDE", "Ferric ferrocyanide"),
    "77007": ("ci-77007", "ULTRAMARINES", "Ultramarines"),
    "77266": ("ci-77266", "CI 77266", "Carbon black"),
    "75470": ("ci-75470", "CARMINE", "Carmine"),
    "15850": ("ci-15850", "CI 15850", "Red 6 / Red 7 and their lakes"),
    "15985": ("ci-15985", "CI 15985", "Yellow 6 and its lake"),
    "16035": ("ci-16035", "CI 16035", "Red 40 and its lake"),
    "17200": ("ci-17200", "CI 17200", "Red 33 and its lake"),
    "19140": ("ci-19140", "CI 19140", "Yellow 5 and its lake"),
    "42090": ("ci-42090", "CI 42090", "Blue 1 and its lake"),
    "45380": ("ci-45380", "CI 45380", "Red 21 / Red 22 and their lakes"),
    "45410": ("ci-45410", "CI 45410", "Red 27 / Red 28 and their lakes"),
    "73360": ("ci-73360", "CI 73360", "Red 30 and its lake"),
}
# Printed names that differ only by translation or synonym -> one INCI name.
ALIASES = {
    "cera alba": "BEESWAX", "beeswax": "BEESWAX",
    "euphorbia cerifera (candelilla) wax": "EUPHORBIA CERIFERA (CANDELILLA) WAX",
    "candelilla cera": "EUPHORBIA CERIFERA (CANDELILLA) WAX",
    "copernicia cerifera (carnauba) wax": "COPERNICIA CERIFERA (CARNAUBA) WAX",
    "cera carnauba": "COPERNICIA CERIFERA (CARNAUBA) WAX", "copernicia cerifera cera": "COPERNICIA CERIFERA (CARNAUBA) WAX",
    "microcrystalline wax": "MICROCRYSTALLINE WAX", "cera microcristallina": "MICROCRYSTALLINE WAX",
    "aqua": "WATER", "water": "WATER", "parfum": "FRAGRANCE", "fragrance": "FRAGRANCE",
    "aroma": "FLAVOR", "flavor": "FLAVOR",
}
# Brands print the same wax or carrier in English, Latin and French, in varying order.
KEYWORDS = [
    (r"candelilla", "EUPHORBIA CERIFERA (CANDELILLA) WAX"),
    (r"carnauba", "COPERNICIA CERIFERA (CARNAUBA) WAX"),
    (r"microcrystalline wax|cera microcristallina", "MICROCRYSTALLINE WAX"),
    (r"^(?!synthetic).*(cera alba|beeswax)", "BEESWAX"),
    (r"^(aqua|water)\b", "WATER"),
    (r"^(parfum|fragrance)\b", "FRAGRANCE"),
    (r"^(aroma|flavor)\b", "FLAVOR"),
]
MAY_CONTAIN = re.compile(r"(\[\s*\+/-\s*:?|may contain\s*/\s*peut contenir\s*(\(±\))?\s*:?|may contain\s*:?)", re.I)


def split_top(text, seps):
    """Split on separators that are not inside parentheses or brackets."""
    items, depth, cur = [], 0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        sep = next((s for s in seps if depth == 0 and text.startswith(s, i)), None)
        if sep:
            items.append(cur); cur = ""; i += len(sep); continue
        cur += ch
        i += 1
    items.append(cur)
    return [x.strip(" .;: ") for x in items if x.strip(" .;: ")]


def items_from_label(label):
    """Return a list of (name_as_printed, may_contain) in label order."""
    label = re.sub(r"^\s*ingredients\s*:\s*", "", label.strip(), flags=re.I)
    seps = [" • "] if "•" in label else [", "]
    m = MAY_CONTAIN.search(label)
    main, extra = (label[:m.start()], label[m.end():]) if m else (label, "")
    extra = extra.strip().strip("[]").strip()
    out = [(x, "no") for x in split_top(main, seps)]
    for x in split_top(extra, seps + [", "]):
        out.append((x, "yes"))
    return out


def normalize(name):
    """Return list of (ingredient_id, inci_name, common_name) for one printed item.

    One printed item can hold several colorants, e.g. "Iron Oxides (CI 77491, CI 77492)".
    """
    cis = re.findall(r"ci\s*(\d{5})", name, re.I)
    if cis:
        return [COLORANTS.get(c, (f"ci-{c}", f"CI {c}", f"CI {c}")) for c in dict.fromkeys(cis)]
    if re.fullmatch(r"(?i)titanium dioxide", name.strip()):
        return [COLORANTS["77891"]]
    if re.fullmatch(r"(?i)iron oxides?", name.strip()):
        return [("iron-oxides-unspecified", "IRON OXIDES", "Iron oxides")]
    low = name.lower()
    for pattern, inci in KEYWORDS:
        if re.search(pattern, low):
            iid = re.sub(r"[^a-z0-9]+", "-", inci.lower()).strip("-")
            return [(iid, inci, inci.title())]
    parts = [p.strip() for p in name.split("/")]
    for p in parts:
        key = p.lower()
        if key in ALIASES:
            inci = ALIASES[key]
            break
    else:
        # Drop French duplicates such as "Cire de Candelilla".
        parts = [p for p in parts if not p.lower().startswith(("cire ", "eau", "peut "))]
        inci = "/".join(parts).upper()
    inci = re.sub(r"\s+", " ", inci).strip()
    iid = re.sub(r"[^a-z0-9]+", "-", inci.lower()).strip("-")
    return [(iid, inci, inci.title())]
