#!/usr/bin/env python3
"""Build The Lip Ledger static website from the database.

Usage: python3 scripts/build_site.py [data_dir] [out_dir]
Defaults: data/ and docs/. Every page is generated from the CSV files and the
rating rules in rate.py; nothing on the site is written by hand except the
fixed explanatory text in this file.
"""
import hashlib
import html
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rate  # noqa: E402

SITE = "The Lip Ledger"
LOOK = ("Evidence of harm", "Known allergen", "Unclear")
TONE = {"Evidence of harm": "h", "Known allergen": "a", "Unclear": "u",
        "No concerns found": "c", "No research found": "n"}
ROUTE_NAME = {"dermal": "On skin and lips", "oral": "Swallowed", "inhalation": "Breathed in", "eye": "Near the eyes"}
ROUTE_SHORT = {"dermal": "Skin", "oral": "Swallowed", "inhalation": "Breathed in", "eye": "Eyes"}
CATEGORY = {"lipstick": "Lipstick", "liquid_lipstick": "Liquid lipstick", "lip_gloss": "Lip gloss",
            "lip_liner": "Lip liner", "lip_balm": "Tinted lip balm",
            "lip_balm_spf": "SPF lip balm", "lip_gloss_spf": "SPF lip gloss"}
# Lip products with sunscreen. In the US these are over-the-counter drugs, so their labels
# list "active ingredients" (the UV filters and skin protectants) separately.
SPF = {"lip_balm_spf", "lip_gloss_spf"}
JURIS = {"US_FDA": "US FDA", "EU": "EU", "California": "California", "Canada": "Canada"}
STATUS = {"allowed": "Allowed", "restricted": "Restricted", "banned": "Banned", "allergen_listed": "Listed as an allergen"}
RESULT = {"harm": "Found harm", "no_harm": "Found no harm", "inconclusive": "Could not decide"}
# Illustration colors are decorative and are not the products' real shades.
TINTS = [("#B9605A", "#F6E7E1"), ("#8E2F4F", "#F1E2E8"), ("#C8566A", "#F8E6E6"),
         ("#E2A08A", "#FBEDE4"), ("#9E3B2F", "#F5E4DC"), ("#B0476B", "#F4E3EA")]

DISCLAIMER = ("<strong>For information only.</strong> We summarize published research and regulator decisions. "
              "This is not medical, safety or legal advice. For questions about an ingredient's safety, consult a "
              "toxicologist. For a reaction or a skin condition, see a dermatologist or doctor.")

e = html.escape


def fmt_date(iso):
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def ing_name(i):
    c = i["common_name"]
    if c and c.upper() != c:
        return c
    return i["inci_name"].title()


def full_name(site, pid):
    p = site.products[pid]
    brand = site.brands[p["brand_id"]]["name"]
    return p["name"] if p["name"].lower().startswith(brand.lower()) else f"{brand} {p['name']}"


def tag(rating, extra=""):
    return f'<span class="tag t-{TONE[rating]}{extra}">{e(rating)}</span>'


def nice(text):
    for k, v in JURIS.items():
        text = text.replace(k, v)
    return text


# ---------------------------------------------------------------- data model

class Site:
    def __init__(self, data_dir):
        db = rate.load(data_dir)
        schema = json.loads((Path(__file__).resolve().parent.parent / "data" / "schema.json").read_text())
        errors = rate.validate(db, schema)
        if errors:
            raise SystemExit("Validation failed:\n  " + "\n  ".join(errors))
        self.db = db
        self.sources = {s["source_id"]: s for s in db["sources"]}
        self.brands = {b["brand_id"]: b for b in db["brands"]}
        self.products = {p["product_id"]: p for p in db["products"]}
        self.ings = {i["ingredient_id"]: i for i in db["ingredients"]}
        self.findings = defaultdict(list)
        for f in db["findings"]:
            self.findings[f["ingredient_id"]].append(f)
        self.regs = defaultdict(list)
        for r in db["regulatory_status"]:
            self.regs[r["ingredient_id"]].append(r)
        self.routes_for = defaultdict(list)
        for cr in db["category_routes"]:
            self.routes_for[cr["category"]].append(cr["route"])
        self.lists = defaultdict(list)
        for lst in db["ingredient_lists"]:
            self.lists[lst["product_id"]].append(lst)
        self.items = defaultdict(list)
        for li in db["list_items"]:
            self.items[li["list_id"]].append(li)
        for v in self.items.values():
            v.sort(key=lambda x: int(x["position"]))

        self.rating = {}
        for iid in self.ings:
            for route in rate.ROUTES:
                self.rating[(iid, route)] = rate.rate(iid, route, self.findings[iid], self.regs[iid], self.sources)

        self.lip_rating = {iid: self.combined(iid, ["dermal", "oral"]) for iid in self.ings}
        self.used_in = defaultdict(set)
        for pid, lists in self.lists.items():
            for lst in lists:
                for li in self.items[lst["list_id"]]:
                    self.used_in[li["ingredient_id"]].add(pid)

    def combined(self, iid, routes):
        return min((self.rating[(iid, r)][0] for r in routes), key=rate.SUMMARY_ORDER.index)

    def product_rating(self, pid, iid):
        return self.combined(iid, self.routes_for[self.products[pid]["category"]])

    def counts(self, pid, ingredient_ids):
        c = Counter(self.product_rating(pid, iid) for iid in ingredient_ids)
        return {"n": len(ingredient_ids), "clear": c["No concerns found"], "none": c["No research found"],
                "look": sum(c[k] for k in LOOK)}

    def product_ingredients(self, pid):
        seen = []
        for lst in self.lists[pid]:
            for li in self.items[lst["list_id"]]:
                if li["ingredient_id"] not in seen:
                    seen.append(li["ingredient_id"])
        return seen

    def counted(self, f):
        return rate.usable(f, self.sources)


# ---------------------------------------------------------------- page parts

def page(title, root, body, description=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description or 'What the research says about the ingredients in popular lipsticks.')}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&amp;family=Inter:wght@400;500;600&amp;display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}assets/style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top wrap">
  <a class="brand" href="{root}">{SITE}</a>
  <nav aria-label="Main">
    <a href="{root}">Lipsticks</a>
    <a href="{root}#spf">SPF lip</a>
    <a href="{root}ingredients/">Ingredients</a>
    <a href="{root}top-lists/">Top lists</a>
    <a href="{root}how-we-rate/">How we rate</a>
    <a href="{root}about/">About and disclaimer</a>
  </nav>
</header>
<aside class="wrap" aria-label="Disclaimer"><p class="disclaimer" role="note">{DISCLAIMER}</p></aside>
<main id="main" class="wrap">
{body}
</main>
<footer class="foot wrap">
  <p>{SITE} rates ingredients, not products. Ratings are produced automatically by fixed rules from full safety reports and regulations, and have not yet been reviewed by an independent toxicologist. Ingredient lists can change: always check the label on your product. Brand and product names are used only to identify products; {SITE} is not affiliated with any brand.</p>
  <p><a href="{root}how-we-rate/">How we rate</a> · <a href="{root}about/">About and disclaimer</a></p>
</footer>
<script src="{root}assets/site.js" defer></script>
</body>
</html>
"""


def illustration(pid, category, size="card"):
    h = int(hashlib.sha1(pid.encode()).hexdigest(), 16)
    tint, bg = TINTS[h % len(TINTS)]
    if category in ("lip_gloss", "lip_gloss_spf"):
        art = (f'<rect x="27" y="4" width="26" height="54" rx="5" fill="#2A1A22"/>'
               f'<rect x="31" y="8" width="4" height="46" rx="2" fill="#FFFFFF" opacity="0.2"/>'
               f'<rect x="22" y="58" width="36" height="98" rx="8" fill="{tint}" opacity="0.9"/>'
               f'<rect x="27" y="64" width="6" height="84" rx="3" fill="#FFFFFF" opacity="0.35"/>')
    elif category in ("lip_balm", "lip_balm_spf"):
        art = (f'<path d="M28 40 Q28 30 40 28 Q52 30 52 40 L52 70 L28 70 Z" fill="{tint}"/>'
               f'<rect x="22" y="70" width="36" height="16" rx="2" fill="#C9A86A"/>'
               f'<rect x="18" y="86" width="44" height="70" rx="6" fill="#F4F0EC" stroke="#2A1A22" stroke-width="1.5"/>'
               f'<rect x="23" y="92" width="5" height="58" rx="2" fill="{tint}" opacity="0.35"/>')
    else:
        art = (f'<path d="M27 24 Q27 16 34 13 L53 4 L53 60 L27 60 Z" fill="{tint}"/>'
               f'<rect x="31" y="20" width="4" height="38" rx="2" fill="#FFFFFF" opacity="0.25"/>'
               f'<rect x="23" y="58" width="34" height="26" rx="2" fill="#C9A86A"/>'
               f'<rect x="26" y="60" width="4" height="22" fill="#FFFFFF" opacity="0.35"/>'
               f'<rect x="17" y="84" width="46" height="74" rx="4" fill="#2A1A22"/>'
               f'<rect x="21" y="88" width="5" height="66" rx="2" fill="#FFFFFF" opacity="0.14"/>')
    w, hgt = (90, 180) if size == "card" else (170, 340)
    return bg, f'<svg width="{w}" height="{hgt}" viewBox="0 0 80 160" aria-hidden="true">{art}</svg>'


def bar(c):
    n = c["n"] or 1
    a, b = 100 * c["clear"] / n, 100 * c["none"] / n
    label = f'{c["clear"]} no concerns found, {c["none"]} not yet researched, {c["look"]} worth a closer look'
    return (f'<svg class="bar" width="100%" height="12" viewBox="0 0 100 12" preserveAspectRatio="none" role="img" '
            f'aria-label="{label}"><rect x="0" y="0" width="{a:.2f}" height="12" fill="#2A6CB8"/>'
            f'<rect x="{a:.2f}" y="0" width="{b:.2f}" height="12" fill="#B3A7A2"/>'
            f'<rect x="{a + b:.2f}" y="0" width="{100 - a - b:.2f}" height="12" fill="#C99A1E"/></svg>')


def legend(c):
    return (f'<span class="legend"><span><span class="dot d-c"></span>No concerns found {c["clear"]}</span>'
            f'<span><span class="dot d-n"></span>Not yet researched {c["none"]}</span>'
            f'<span><span class="dot d-u"></span>Worth a closer look {c["look"]}</span></span>')


def source_line(s, root=""):
    cite = e(s["citation"])
    url = s["url"]
    return f'<a href="{e(url)}" rel="noopener">{cite}</a>' if url else cite


def counted_reasons(site, iid, route):
    """Plain-language evidence behind one ingredient-route rating (counted items only)."""
    out = []
    for f in site.findings[iid]:
        if f["route"] in (route, "lab_only") and site.counted(f):
            out.append(f["summary"])
    for r in site.regs[iid]:
        if rate.route_matches(r["route"], route):
            out.append(f'{STATUS[r["status"]]} by the {JURIS[r["jurisdiction"]]}'
                       + (f': {r["limit_text"]}' if r["limit_text"] else "") + ".")
    return out


# ---------------------------------------------------------------- pages

def home(site):
    cards, spf_cards = [], []
    index = []
    for pid, p in site.products.items():
        if not site.lists[pid]:
            continue
        brand = site.brands[p["brand_id"]]["name"]
        ids = site.product_ingredients(pid)
        c = site.counts(pid, ids)
        bg, art = illustration(pid, p["category"])
        names = [ing_name(site.ings[i]) for i in ids]
        shades = len(site.lists[pid])
        sub = f'{c["n"]} ingredients' + (f' across {shades} shade labels' if shades > 1 else "")
        (spf_cards if p["category"] in SPF else cards).append(f'''<a class="card" href="lipsticks/{pid}/" data-search="{e((brand + " " + p["name"] + " " + " ".join(names)).lower())}">
  <span class="art" style="background:{bg}">{art}</span>
  <span class="card-body">
    <span class="eyebrow">{e(brand)} · {e(CATEGORY.get(p["category"], p["category"]))}</span>
    <span class="card-title">{e(p["name"])}</span>
    <span class="muted">{sub}{spf_line(site, pid)}</span>
    {bar(c)}
    {legend(c)}
    <span class="hit muted" hidden></span>
  </span>
</a>''')
        index.append({"pid": pid, "names": names})
    hero = f'''<section class="hero">
  <span class="kicker">Research, not rumors</span>
  <h1>What's really in your lipstick?</h1>
  <p class="lede">We read the full safety reports and regulations behind each ingredient. Search a lipstick, an SPF lip balm or an ingredient to see what the evidence says, and where it is still missing.</p>
  <form class="search" role="search" onsubmit="return false">
    <label for="q">Search lipsticks or ingredients</label>
    <input id="q" type="search" placeholder="Glossier, Gloss Bomb, mica, SPF..." autocomplete="off">
  </form>
</section>'''
    body = f'''{hero}
<section class="stack">
  <h2>Lipsticks</h2>
  <p id="none" class="muted" hidden>Nothing matches yet. Try an ingredient name, or <a href="ingredients/">browse all ingredients</a>.</p>
  <div class="grid">
{chr(10).join(cards)}
  </div>
</section>
<section class="stack" id="spf">
  <h2>SPF lip balms and glosses</h2>
  <p class="muted">Lip products with sunscreen are sold as over-the-counter drugs in the US, so their labels list the sunscreen "active ingredients" first. We rate those the same way as every other ingredient. A rating is about the ingredient, never a reason to skip sun protection.</p>
  <div class="grid">
{chr(10).join(spf_cards)}
  </div>
</section>
<section class="key">
  <h2>What the ratings mean</h2>
  <ul class="key-list">
    <li>{tag("Evidence of harm")} A regulator banned or restricted it for safety, or strong evidence found harm at cosmetic levels.</li>
    <li>{tag("Known allergen")} A regulator lists it as a cosmetic allergen, or human patch tests show allergy.</li>
    <li>{tag("Unclear")} The evidence is limited, mixed, or the experts could not decide.</li>
    <li>{tag("No concerns found")} Full safety reports or a regulator approval found no harm at cosmetic use.</li>
    <li>{tag("No research found")} We have not found a full safety report yet. A gap in the research is not a sign of harm.</li>
  </ul>
  <p class="muted">Ratings describe single ingredients for the ways lipstick reaches you (skin contact and the small amount you swallow). They are not a verdict on any product. <a href="how-we-rate/">How we rate</a></p>
</section>'''
    return page(f"{SITE}: what's really in your lipstick", "", body)


def product_page(site, pid):
    p = site.products[pid]
    brand = site.brands[p["brand_id"]]
    root = "../../"
    lists = site.lists[pid]
    routes = site.routes_for[p["category"]]
    bg, art = illustration(pid, p["category"], "hero")
    host = p["retailer_url"].split("/")[2].removeprefix("www.") if p["retailer_url"] else ""

    sections = []
    for k, lst in enumerate(lists):
        ids = [li["ingredient_id"] for li in site.items[lst["list_id"]]]
        c = site.counts(pid, ids)
        shade = lst["shade"].replace("\n", " ").strip()
        look, none = [], []
        rows = []
        for li in site.items[lst["list_id"]]:
            iid = li["ingredient_id"]
            ing = site.ings[iid]
            r = site.product_rating(pid, iid)
            name = ing_name(ing)
            if r in LOOK:
                notes = []
                for route in routes:
                    rr = site.rating[(iid, route)][0]
                    why = " ".join(e(x) for x in counted_reasons(site, iid, route)) if rr in LOOK else ""
                    notes.append(f'<li><strong>{ROUTE_SHORT[route]}:</strong> {e(rr)}. {why}</li>')
                look.append(f'''<div class="look">
  <div class="look-text">
    <span class="look-title"><span class="h3">{e(name)}</span>{tag(r)}</span>
    <ul class="plain">{"".join(notes)}</ul>
  </div>
  <a class="btn" href="{root}ingredients/{iid}/">See the evidence &rarr;</a>
</div>''')
            if r == "No research found":
                none.append(f'<a class="tag t-n chip" href="{root}ingredients/{iid}/">{e(name)}</a>')
            per = " · ".join(f'{ROUTE_SHORT[route]}: {e(site.rating[(iid, route)][0])}' for route in routes)
            reasons = []
            for route in routes:
                rs = counted_reasons(site, iid, route)
                if rs:
                    reasons.append(f'<p><strong>{ROUTE_SHORT[route]}.</strong> {e(rs[0])}</p>')
            if not reasons:
                reasons.append("<p>We have not found a full safety report or regulator decision for this ingredient yet.</p>")
            printed = li["name_as_printed"]
            label_note = f'<p class="muted">On the label as: {e(printed)}</p>' if printed and printed.lower() != name.lower() else ""
            mc = '<p class="muted">Listed under "may contain", so it is only in some shades.</p>' if li["may_contain"] == "yes" else ""
            if li.get("active") == "yes":
                mc += ('<p class="muted">An active ingredient on the US Drug Facts label (as printed: '
                       f'{e(printed)}). Sunscreen and skin protectant actives are regulated by the FDA as drugs.</p>')
            rows.append(f'''<details class="irow" data-grp="{"look" if r in LOOK else ("none" if r == "No research found" else "clear")}">
  <summary><span class="pos">{e(li["position"])}</span><span class="dot d-{TONE[r]}"></span><span class="iname">{e(name)}{' <span class="act">Active</span>' if li.get("active") == "yes" else ""}</span><span class="ilabel">{e(r)}</span></summary>
  <div class="idetail">
    <p class="muted">{per}</p>
    {"".join(reasons)}{label_note}{mc}
    <p><a href="{root}ingredients/{iid}/">All evidence for {e(name)} &rarr;</a></p>
  </div>
</details>''')
        look_html = (f'<section class="stack"><h2>Worth a closer look</h2>{"".join(look)}</section>' if look else
                     '<section class="stack"><h2>Worth a closer look</h2><p class="muted">No ingredient on this label is rated Evidence of harm, Known allergen or Unclear for lip use.</p></section>')
        none_html = (f'''<section class="stack"><h2>Not yet researched</h2>
<p class="muted">We have not found a full safety report for these yet. A gap in the research is not a sign of harm.</p>
<div class="chips">{"".join(none)}</div></section>''' if none else "")
        sections.append(f'''<div class="shade" data-shade="{k}"{" hidden" if k else ""}>
<div class="summary-box">
  <span class="h3"><span class="blue">{c["clear"]} of {c["n"]}</span> ingredients: no concerns found</span>
  {bar(c)}
  {legend(c)}
  <span class="muted">Label from <a href="{e(lst["source_url"] or p["retailer_url"])}" rel="noopener">{e(host)}</a>, checked {fmt_date(lst["captured_on"])}{(" · Shade: " + e(shade)) if shade else ""}</span>
</div>
{look_html}
{none_html}
<section class="list-wrap">
  <div class="stack list-main">
    <div class="list-head">
      <div><h2>Full ingredient list</h2><span class="muted">In label order, from most to least. Tap any ingredient for details.</span></div>
      <div class="filters" role="group" aria-label="Show">
        <button type="button" class="fbtn on" data-f="all">All</button>
        <button type="button" class="fbtn" data-f="look">Closer look</button>
        <button type="button" class="fbtn" data-f="none">Not researched</button>
      </div>
    </div>
    <div class="ilist">{"".join(rows)}</div>
  </div>
  <aside class="howto">
    <h3>How to read this</h3>
    <p>Each ingredient is rated on its own for the ways a {e(CATEGORY.get(p["category"], "lip product").lower())} reaches you: {" and ".join(ROUTE_NAME[r].lower() for r in routes)}. The list shows the more cautious of the ratings, and "not yet researched" counts as more cautious than "no concerns found".</p>
    <p>A rating is about the ingredient at typical cosmetic use. It is not a verdict on this product.</p>
    <p class="muted">Ingredient lists can change. Always check the label on your product.</p>
  </aside>
</section>
</div>''')

    if len(lists) > 1:
        opts = "".join(f'<option value="{k}">{e(l["shade"].replace(chr(10), " ").strip() or "All other shades")}</option>'
                       for k, l in enumerate(lists))
        picker = f'''<div class="picker"><label for="shade">This brand prints a separate label for different shades. Choose a shade:</label>
<select id="shade">{opts}</select></div>'''
    else:
        picker = ""
    shade_note = f"{len(lists)} shade labels" if len(lists) > 1 else "one label for all shades"
    body = f'''<nav class="crumbs" aria-label="Breadcrumb"><a href="{root}">Lipsticks</a><span aria-hidden="true">/</span><span>{e(brand["name"])}</span><span aria-hidden="true">/</span><span>{e(p["name"])}</span></nav>
<section class="phero">
  <div class="part" style="background:{bg}">{art}<span class="cap">Illustration, not the real shade. Product photo coming soon.</span></div>
  <div class="ptext">
    <span class="eyebrow">{e(brand["name"])} · {e(CATEGORY.get(p["category"], p["category"]))}</span>
    <h1>{e(p["name"])}</h1>
    <span class="muted">{len(site.product_ingredients(pid))} ingredients · {shade_note}</span>
    {spf_hero(site, pid)}
    {picker}
  </div>
</section>
{"".join(sections)}'''
    return page(f'{brand["name"]} {p["name"]}: ingredients | {SITE}', root, body,
                f'What the research says about each ingredient in {brand["name"]} {p["name"]}.')


def actives(site, pid):
    """Active ingredients as printed on the first label, e.g. ["Avobenzone 3%", ...]."""
    lists = site.lists[pid]
    return [li["name_as_printed"] for li in site.items[lists[0]["list_id"]] if li.get("active") == "yes"] if lists else []


def spf_line(site, pid):
    acts = actives(site, pid)
    return f' · Actives: {e(", ".join(acts))}' if acts else ""


def spf_hero(site, pid):
    acts = actives(site, pid)
    if not acts:
        return ""
    return (f'<p class="spf-note"><strong>Active ingredients:</strong> {e(", ".join(acts))}. '
            'These are listed first below. Ratings cover the ingredients only; they never suggest skipping sun protection. '
            f'<a href="{"../../"}how-we-rate/#spf">How we rate sunscreen ingredients</a></p>')


def evidence_item(site, f, counted):
    s = site.sources[f["source_id"]]
    year = s["year"] or ""
    quote = f'<blockquote>“{e(f["quote"])}”</blockquote>' if f["quote"] else ""
    if counted:
        status = f'<span class="result r-{f["result"]}">{RESULT[f["result"]]}</span>'
    else:
        why = {"summary_only": "We could only read a summary of this document, not the full text, so it does not count toward the rating.",
               "abstract_only": "We could only read the abstract, not the full paper, so it does not count toward the rating."}.get(
            f["what_was_read"], "This source does not meet our quality rules, so it does not count toward the rating.")
        status = f'<span class="result r-not">Not counted</span><p class="muted">{why}</p>'
    return f'''<li class="ev">
  <div class="ev-head"><span class="ev-year">{e(year)}</span>{status}</div>
  <p>{e(f["summary"])}</p>{quote}
  <p class="muted">{source_line(s)}</p>
</li>'''


def reg_item(site, r):
    s = site.sources[r["source_id"]]
    return f'''<li class="ev">
  <div class="ev-head"><span class="ev-year">{e(s["year"] or r["effective_date"] or "")}</span><span class="result r-reg">{STATUS[r["status"]]} · {JURIS[r["jurisdiction"]]}</span></div>
  {f"<p>{e(r['limit_text'])}</p>" if r["limit_text"] else ""}
  <p class="muted">{source_line(s)}</p>
</li>'''


def ingredient_page(site, iid):
    ing = site.ings[iid]
    root = "../../"
    name = ing_name(ing)
    lip = site.lip_rating[iid]
    facts = [("INCI name", ing["inci_name"]), ("CAS number", ing["cas"]), ("Color index", ing["ci_number"]),
             ("Used as", ing["functions"].replace(";", ", ")), ("Also called", ing["synonyms"].replace(";", ", "))]
    facts_html = "".join(f"<div><dt>{k}</dt><dd>{e(v)}</dd></div>" for k, v in facts if v)

    def route_block(route, big):
        rating, reason, _ = site.rating[(iid, route)]
        counted = [f for f in site.findings[iid] if f["route"] in (route, "lab_only") and site.counted(f)]
        regs = [r for r in site.regs[iid] if rate.route_matches(r["route"], route)]
        ignored = [f for f in site.findings[iid] if f["route"] == route and not site.counted(f)]
        items = [evidence_item(site, f, True) for f in counted] + [reg_item(site, r) for r in regs]
        items += [evidence_item(site, f, False) for f in ignored]
        ev = f'<ul class="evlist">{"".join(items)}</ul>' if items else \
            '<p class="muted">We have not found a full safety report, study or regulator decision for this route yet.</p>'
        return f'''<section class="route{" big" if big else ""}" id="{route}">
  <div class="route-head"><h3>{ROUTE_NAME[route]}</h3>{tag(rating)}</div>
  <p class="muted">Why: {e(nice(reason))}.</p>
  {ev}
</section>'''

    used = sorted(site.used_in[iid], key=lambda pid: site.products[pid]["name"])
    found = "".join(f'<li><a href="{root}lipsticks/{pid}/">{e(full_name(site, pid))}</a></li>' for pid in used)
    body = f'''<nav class="crumbs" aria-label="Breadcrumb"><a href="{root}ingredients/">Ingredients</a><span aria-hidden="true">/</span><span>{e(name)}</span></nav>
<section class="ihero">
  <span class="eyebrow">Ingredient</span>
  <h1>{e(name)}</h1>
  <div class="lip-verdict"><span>In lip products:</span>{tag(lip)}</div>
  <p class="muted">Lip products reach you two ways: through skin contact, and the small amount you swallow. The rating above is the more cautious of the two. Ratings for other ways people are exposed apply to other kinds of products.</p>
  {f'<dl class="facts">{facts_html}</dl>' if facts_html else ""}
</section>
<div class="routes">
{route_block("dermal", True)}
{route_block("oral", True)}
</div>
<details class="other">
  <summary>Other ways people are exposed (for powders, sprays and eye products)</summary>
  <div class="routes">{route_block("inhalation", False)}{route_block("eye", False)}</div>
</details>
<section class="stack">
  <h2>Found in</h2>
  {f'<ul class="found">{found}</ul>' if found else '<p class="muted">None of the products we have checked so far.</p>'}
</section>
<p class="muted">Expert panel reports from the Cosmetic Ingredient Review are funded by the cosmetics industry (the Personal Care Products Council). We use them because they review the published research in full, and we say so every time we cite one.</p>'''
    return page(f"{name}: what the research says | {SITE}", root, body,
                f"What full safety reports and regulators say about {name} in lip products.")


def ingredients_index(site):
    root = "../"
    rows = []
    for iid in sorted(site.ings, key=lambda i: ing_name(site.ings[i]).lower()):
        if not site.used_in[iid]:
            continue
        r = site.lip_rating[iid]
        name = ing_name(site.ings[iid])
        n = len(site.used_in[iid])
        rows.append(f'<li data-r="{TONE[r]}" data-search="{e((name + " " + site.ings[iid]["inci_name"] + " " + site.ings[iid]["synonyms"]).lower())}">'
                    f'<a href="{iid}/">{e(name)}</a><span class="muted">in {n} product{"s" if n != 1 else ""}</span>{tag(r)}</li>')
    counts = Counter(site.lip_rating[i] for i in site.ings if site.used_in[i])
    filt = "".join(f'<button type="button" class="fbtn" data-r="{TONE[k]}">{e(k)} ({counts[k]})</button>'
                   for k in rate.RATINGS if counts[k])
    body = f'''<section class="ihero">
  <h1>Ingredients</h1>
  <p class="lede">Every ingredient on the labels we have checked, rated for use in lip products.</p>
  <form class="search" role="search" onsubmit="return false"><label for="iq">Search ingredients</label>
  <input id="iq" type="search" placeholder="titanium dioxide, castor oil, mica..." autocomplete="off"></form>
  <div class="filters" role="group" aria-label="Filter by rating"><button type="button" class="fbtn on" data-r="">All ({sum(counts.values())})</button>{filt}</div>
</section>
<ul class="alist">{"".join(rows)}</ul>
<p id="inone" class="muted" hidden>No ingredient matches.</p>'''
    return page(f"Ingredients | {SITE}", root, body)


def how_page():
    body = f'''<article class="prose">
<h1>How we rate</h1>
<p class="lede">Every rating on this site is produced automatically by the same fixed rules. Nobody picks a rating by hand, and no brand pays to be listed or rated.</p>
<h2>We rate ingredients, not products</h2>
<p>Each ingredient gets a rating for each way people are exposed to it: on the skin and lips, swallowed, breathed in, and near the eyes. For a lipstick we look at skin contact and swallowing, and show the more cautious of the two. We never give a product an overall safe or unsafe verdict.</p>
<h2>The five ratings</h2>
<p>For each ingredient and route, the first rule that matches decides the rating.</p>
<ol>
<li>{tag("Evidence of harm")} The EU, US, California or Canada banned or restricted it for safety; or the International Agency for Research on Cancer put it in Group 1 or 2A for this route; or a regulator, an expert panel or a human study found harm at the amounts used in cosmetics.</li>
<li>{tag("Known allergen")} A regulator lists it as a cosmetic allergen, or human patch-test or clinical studies show allergy.</li>
<li>{tag("Unclear")} Harm or uncertain results appear only in animal or lab studies, at doses far above cosmetic use, or the experts said the data were not enough to decide.</li>
<li>{tag("No concerns found")} Reliable studies or full safety assessments looked and found no harm for this route, or a regulator approved it for this use (for example, a US FDA color additive listing that covers lip products).</li>
<li>{tag("No research found")} We have nothing reliable on record for this route yet. This means the research is missing or we have not reached it. It is not a sign of harm.</li>
</ol>
<h2>Which evidence counts</h2>
<ul>
<li><strong>Full texts only.</strong> We count a report or paper only if we read the whole document. An abstract or a summary is not enough. When a full text is paywalled or blocked, we list the source as "not counted". The one exception is a cancer classification from the International Agency for Research on Cancer, where the official classification itself is the finding.</li>
<li><strong>Reputable sources only.</strong> Regulations and opinions from government safety bodies count. Individual studies count only if they are peer-reviewed and rated reliable on the Klimisch scale used by EU and OECD chemical assessors.</li>
<li><strong>Expert panel reports.</strong> Many ratings come from the Cosmetic Ingredient Review (CIR) Expert Panel, which reads the published research on an ingredient in full. The panel is funded by the cosmetics industry, and we note this wherever we cite it. We record a CIR conclusion only when the report names the ingredient in its conclusion.</li>
<li><strong>Swallowing.</strong> A CIR conclusion counts for swallowing when the full report includes lip-product uses, where small amounts are swallowed.</li>
</ul>
<h2 id="spf">Sunscreen ingredients</h2>
<p>SPF lip products are over-the-counter drugs in the US, so their labels list "active ingredients" (the UV filters, and skin protectants such as petrolatum) before the other ingredients. We rate each active ingredient with the same rules as everything else.</p>
<ul>
<li><strong>US FDA.</strong> The FDA's sunscreen monograph lists the active ingredients a sunscreen may use. In its 2021 proposal to update that list, the FDA found enough safety data only for zinc oxide and titanium dioxide. For 12 others, including avobenzone, homosalate, octinoxate, octisalate, octocrylene and oxybenzone, it asked for more data and said this "does not represent a conclusion" that they are unsafe. We record that as <em>Unclear</em>.</li>
<li><strong>Absorption is not harm.</strong> An FDA clinical trial found that common chemical UV filters reach the blood. That tells us more safety data are needed. It does not show harm, and the authors said people should keep using sunscreen.</li>
<li><strong>EU limits.</strong> The EU has lowered the allowed amounts of some UV filters. We will add those rules once we have read the official texts in full.</li>
<li><strong>Swallowing.</strong> The FDA's sunscreen review is about skin. Unless another full report covers swallowing, a UV filter shows <em>No research found</em> for that route.</li>
</ul>
<p>Using sunscreen lowers the risk of sunburn and skin cancer. Nothing on this site is advice to stop using it. Ask a dermatologist which product suits you.</p>
<h2>What we do not use</h2>
<p>We do not use rating apps, scores from advocacy groups, social media, or brand marketing as evidence. Those can point us to a question, but the answer has to come from the primary research or a regulator.</p>
<h2>Limits</h2>
<ul>
<li>Our rules and ratings have not yet been reviewed by an independent toxicologist.</li>
<li>Dose matters. A substance can be harmful at high doses and harmless at the tiny amounts in a lipstick. Our ratings follow what the sources concluded about cosmetic use.</li>
<li>Ingredient lists come from each brand's official website on the date shown. Brands change formulas, so the label on your product is what counts.</li>
<li>Many ingredients have no full safety report we can read yet. As we add sources, ratings can change.</li>
</ul>
</article>'''
    return page(f"How we rate | {SITE}", "../", body)


def about_page():
    body = f'''<article class="prose">
<h1>About and disclaimer</h1>
<p class="lede">{SITE} cuts through rumors about "toxic" makeup by showing what full safety reports and regulators actually say about each ingredient in popular lipsticks and SPF lip products.</p>
<h2>For information only</h2>
<p>Everything on this site is general information. It is not medical, safety or legal advice, and it is not a substitute for advice from a qualified professional.</p>
<ul>
<li>For questions about whether an ingredient is safe, or how much exposure matters, consult a <strong>toxicologist</strong>, a scientist who studies how chemicals affect the body and at what doses.</li>
<li>For an allergic reaction, irritation or any skin condition, see a <strong>dermatologist</strong> or your doctor.</li>
<li>If you think you are having a serious reaction, get medical help right away.</li>
</ul>
<h2>What our ratings are, and are not</h2>
<ul>
<li>Ratings describe individual ingredients at typical cosmetic use. They are not a judgment that any product is safe, unsafe, clean or toxic.</li>
<li>Ratings are produced automatically by fixed rules from the sources we cite. We may have missed research, and sources can be updated after we read them.</li>
<li>"No research found" means we have not found a full safety report yet. It does not mean an ingredient is harmful.</li>
<li>Our rules and ratings have not yet been reviewed by an independent toxicologist.</li>
</ul>
<h2>Products and brands</h2>
<p>Ingredient lists are copied from each brand's official website on the date shown on the product page. Formulas change, and lists can differ by shade or country, so always check the label on your product. Brand and product names are trademarks of their owners and are used only to identify products. {SITE} is not affiliated with, sponsored or endorsed by any brand, and no brand pays to be listed.</p>
<h2>Sources</h2>
<p>We link every source we use. Cosmetic Ingredient Review panel reports are funded by the cosmetics industry, which we note each time. See <a href="../how-we-rate/">How we rate</a> for which sources count and why.</p>
</article>'''
    return page(f"About and disclaimer | {SITE}", "../", body)


# ---------------------------------------------------------------- assets

CSS = r"""
:root{--bg:#FBF7F2;--ink:#2A1A22;--muted:#5E4D55;--line:#E8DED6;--accent:#7A2843;--card:#FFFFFF}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,system-ui,sans-serif;font-size:16px;line-height:1.55}
a{color:var(--accent)}a:hover{color:#561B2F}
a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.skip{position:absolute;left:-999px}.skip:focus{left:16px;top:8px;background:#fff;padding:8px 12px;z-index:10}
.wrap{max-width:1160px;margin:0 auto;padding-left:24px;padding-right:24px}
@media (max-width:600px){.wrap{padding-left:16px;padding-right:16px}}
h1,h2,h3,.h3,.brand,.card-title{font-family:Fraunces,Georgia,serif;font-weight:600;letter-spacing:-0.01em}
h1{font-size:clamp(36px,6vw,60px);line-height:1.05;margin:0}
h2{font-size:clamp(24px,3vw,30px);margin:0}
h3,.h3{font-size:22px;margin:0}
.muted{color:var(--muted);font-size:14px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px 24px;flex-wrap:wrap;padding-top:20px;padding-bottom:12px}
.brand{font-size:26px;font-weight:700;text-decoration:none;color:var(--ink)}
.top nav{display:flex;gap:6px 20px;flex-wrap:wrap;font-size:15px}
.top nav a{padding:8px 0;display:inline-block}
.disclaimer{margin:0 0 8px;background:#FBEFE9;border:1px solid #E8D3C9;border-radius:12px;padding:12px 16px;font-size:14px;line-height:1.55;color:#3B2A31}
main{display:flex;flex-direction:column;gap:40px;padding-top:16px;padding-bottom:56px}
.stack{display:flex;flex-direction:column;gap:14px}
.hero{text-align:center;display:flex;flex-direction:column;align-items:center;gap:16px;padding:32px 0 0}
.kicker,.eyebrow{font-size:13px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--accent)}
.lede{margin:0;font-size:18px;color:var(--muted);max-width:640px}
.search{width:100%;max-width:640px;display:flex;flex-direction:column;gap:8px;text-align:left}
.search label{font-size:14px;font-weight:600}
.search input{font:inherit;font-size:18px;padding:14px 22px;border:1px solid #CDBFB6;border-radius:999px;background:#fff;color:var(--ink);width:100%}
.rank-list{list-style:none;padding:0;margin:0;display:grid;gap:14px}
.rank-row{display:flex;gap:14px;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}
.rank{font-family:Fraunces,serif;font-size:28px;font-weight:700;min-width:2ch;line-height:1}
.rank-body{display:flex;flex-direction:column;gap:6px;flex:1;min-width:0;text-decoration:none;color:inherit}
.count{font-size:.7em;font-weight:400}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:20px}
.card{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:20px;overflow:hidden;text-decoration:none;color:inherit}
.card:hover{border-color:var(--accent);color:inherit}
.art{display:flex;align-items:flex-end;justify-content:center;height:190px;padding-top:12px}
.card-body{display:flex;flex-direction:column;gap:8px;padding:20px 22px 22px}
.card-title{font-size:22px;line-height:1.2}
.bar{display:block;border-radius:6px;overflow:hidden}
.legend{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:13px;color:var(--muted)}
.legend>span{display:inline-flex;align-items:center;gap:6px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;flex:0 0 auto}
.d-h{background:#C2410C}.d-a{background:#D97706}.d-u{background:#C99A1E}.d-c{background:#2A6CB8}.d-n{background:#B3A7A2}
.tag{display:inline-flex;align-items:center;padding:4px 12px;border-radius:999px;font-size:13px;font-weight:600;white-space:nowrap;text-decoration:none}
.t-h{background:#F9DED2;color:#8F3200}.t-a{background:#F8E3CC;color:#7A4300}.t-u{background:#F8EBC4;color:#6B4E00}.t-c{background:#DDE8F5;color:#174E8C}.t-n{background:#ECE6E3;color:#5A4E52}
.key{background:#F3ECE6;border-radius:20px;padding:24px;display:flex;flex-direction:column;gap:12px}
.key-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.key-list li{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.key-list .tag{min-width:150px;justify-content:center}
.crumbs{font-size:14px;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap}
.phero{display:flex;flex-wrap:wrap;gap:32px;align-items:stretch}
.part{flex:1 1 300px;min-height:340px;border-radius:28px;display:flex;align-items:flex-end;justify-content:center;position:relative;overflow:hidden}
.cap{position:absolute;left:16px;bottom:12px;right:16px;font-size:12px;color:#6B5A62}
.part svg{margin-bottom:40px;max-width:60%;height:auto}
@media (max-width:600px){.part{min-height:300px}.part svg{width:120px}}
.ptext{flex:999 1 420px;min-width:0;display:flex;flex-direction:column;gap:14px;justify-content:center}
.picker{display:flex;flex-direction:column;gap:6px;font-size:14px}
.picker select{font:inherit;font-size:16px;padding:10px 14px;border:1px solid #CDBFB6;border-radius:12px;background:#fff;max-width:360px;min-height:44px}
.shade{display:flex;flex-direction:column;gap:40px}
.summary-box{display:flex;flex-direction:column;gap:10px;background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px}
.blue{color:#174E8C}
.look{background:#fff;border:1px solid var(--line);border-radius:24px;padding:22px;display:flex;flex-wrap:wrap;gap:16px 20px;align-items:center}
.look-text{flex:999 1 400px;min-width:0;display:flex;flex-direction:column;gap:8px}
.look-title{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.plain{margin:0;padding-left:18px;color:#3E2E36;font-size:15px;display:flex;flex-direction:column;gap:6px}
.btn{flex:0 0 auto;display:inline-flex;align-items:center;min-height:48px;padding:0 22px;border-radius:999px;background:var(--ink);color:#FBF7F2;font-weight:600;font-size:15px;text-decoration:none}
.btn:hover{color:#fff;background:#000}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{font-weight:500;font-size:14px;padding:8px 14px;white-space:normal}
.list-wrap{display:flex;flex-wrap:wrap;gap:32px;align-items:flex-start}
.list-main{flex:999 1 540px;min-width:0}
.list-head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}
.filters{display:flex;gap:8px;flex-wrap:wrap}
.fbtn{font:inherit;font-size:14px;font-weight:600;padding:9px 16px;border-radius:999px;border:1px solid #CDBFB6;background:#fff;color:var(--ink);cursor:pointer;min-height:44px}
.fbtn.on{background:var(--ink);color:#FBF7F2;border-color:var(--ink)}
.ilist{border-bottom:1px solid #EFE6DF}
.irow{border-top:1px solid #EFE6DF}
.irow summary{list-style:none;display:flex;align-items:center;gap:12px;padding:12px 4px;cursor:pointer;min-height:48px}
.irow summary::-webkit-details-marker{display:none}
.irow summary:hover{background:#F7F1EC}
.pos{width:26px;font-size:13px;color:#8A7980;text-align:right;flex:0 0 auto}
.iname{flex:1 1 auto;font-weight:500;min-width:0;overflow-wrap:anywhere}
.ilabel{font-size:13px;color:var(--muted);text-align:right}
.idetail{padding:0 4px 14px 52px;display:flex;flex-direction:column;gap:4px}
.idetail p{margin:0;font-size:15px}
@media (max-width:600px){.idetail{padding-left:4px}.ilabel{max-width:96px}}
.howto{flex:1 1 280px;min-width:0;background:#F3ECE6;border-radius:20px;padding:22px;display:flex;flex-direction:column;gap:10px}
.howto p{margin:0;font-size:14px}
.ihero{display:flex;flex-direction:column;gap:14px}
.act{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600;letter-spacing:.02em;background:#E7EEF8;color:#1F4E89;vertical-align:middle}
.spf-note{margin:6px 0 0;padding:10px 12px;border-radius:12px;background:#F4EFE9;font-size:14px}
.lip-verdict{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-weight:600}
.lip-verdict .tag{font-size:15px;padding:6px 14px}
.facts{display:flex;flex-wrap:wrap;gap:8px 28px;margin:0;font-size:14px}
.facts dt{color:var(--muted)}.facts dd{margin:0;font-weight:500}
.routes{align-items:start;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px}
.route{background:#fff;border:1px solid var(--line);border-radius:20px;padding:22px;display:flex;flex-direction:column;gap:10px;min-width:0}
.route-head{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
.route p{margin:0}
.evlist{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.ev{border-top:1px solid #EFE6DF;padding:12px 0;display:flex;flex-direction:column;gap:6px;overflow-wrap:anywhere}
.ev p{margin:0;font-size:15px}
.ev-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ev-year:empty{display:none}
.ev-year{font-family:Fraunces,Georgia,serif;font-weight:600}
.result{font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;background:#ECE6E3}
.r-no_harm{background:#DDE8F5;color:#174E8C}.r-harm{background:#F9DED2;color:#8F3200}.r-inconclusive{background:#F8EBC4;color:#6B4E00}.r-reg{background:#E7E1F3;color:#3F2D73}.r-not{background:#ECE6E3;color:#5A4E52}
blockquote{margin:0;padding-left:12px;border-left:3px solid var(--line);font-size:14px;color:#3E2E36}
.other{background:#F3ECE6;border-radius:20px;padding:18px 20px}
.other>summary{cursor:pointer;font-weight:600;min-height:32px}
.other .routes{margin-top:16px}
.found{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:6px}
.alist{list-style:none;margin:0;padding:0;border-bottom:1px solid #EFE6DF}
.alist li{display:flex;gap:6px 14px;align-items:center;flex-wrap:wrap;border-top:1px solid #EFE6DF;padding:10px 4px;min-height:48px}
.alist li a{flex:1 1 260px;font-weight:500;overflow-wrap:anywhere}
.prose{max-width:760px;display:flex;flex-direction:column;gap:14px}
.prose h2{margin-top:16px}
.prose p,.prose li{font-size:17px}
.prose ol,.prose ul{margin:0;padding-left:22px;display:flex;flex-direction:column;gap:10px}
.prose ol .tag{margin-right:6px}
.foot{border-top:1px solid var(--line);padding-top:20px;padding-bottom:40px;font-size:13px;color:var(--muted);max-width:1160px}
.foot p{max-width:820px;margin:0 0 8px}
[hidden]{display:none!important}
"""

JS = r"""
(function(){
  var q=document.getElementById('q');
  if(q){
    var cards=[].slice.call(document.querySelectorAll('.card[data-search]'));
    var none=document.getElementById('none');
    q.addEventListener('input',function(){
      var t=q.value.trim().toLowerCase(),shown=0;
      cards.forEach(function(c){
        var ok=!t||c.getAttribute('data-search').indexOf(t)>=0;
        c.hidden=!ok; if(ok)shown++;
        var hit=c.querySelector('.hit');
        var title=c.querySelector('.card-title').textContent.toLowerCase()+' '+c.querySelector('.eyebrow').textContent.toLowerCase();
        if(t&&ok&&title.indexOf(t)<0){hit.textContent='Contains an ingredient matching "'+q.value.trim()+'"';hit.hidden=false;}else{hit.hidden=true;}
      });
      none.hidden=shown>0;
    });
  }
  var sel=document.getElementById('shade');
  if(sel){sel.addEventListener('change',function(){
    [].forEach.call(document.querySelectorAll('.shade'),function(s){s.hidden=s.getAttribute('data-shade')!==sel.value;});
  });}
  [].forEach.call(document.querySelectorAll('.shade'),function(s){
    var btns=s.querySelectorAll('.fbtn[data-f]');
    [].forEach.call(btns,function(b){b.addEventListener('click',function(){
      [].forEach.call(btns,function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',x===b);});
      var f=b.getAttribute('data-f');
      [].forEach.call(s.querySelectorAll('.irow'),function(r){r.hidden=f!=='all'&&r.getAttribute('data-grp')!==f;});
    });});
  });
  var iq=document.getElementById('iq');
  if(iq){
    var rows=[].slice.call(document.querySelectorAll('.alist li')),rf='',inone=document.getElementById('inone');
    var apply=function(){var t=iq.value.trim().toLowerCase(),n=0;rows.forEach(function(r){
      var ok=(!t||r.getAttribute('data-search').indexOf(t)>=0)&&(!rf||r.getAttribute('data-r')===rf);r.hidden=!ok;if(ok)n++;});inone.hidden=n>0;};
    iq.addEventListener('input',apply);
    var fb=document.querySelectorAll('.fbtn[data-r]');
    [].forEach.call(fb,function(b){b.addEventListener('click',function(){rf=b.getAttribute('data-r');
      [].forEach.call(fb,function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',x===b);});apply();});});
  }
})();
"""

# Printed names that mean added scent or flavor. A fact about the label, not a rating.
SCENT_IDS = {"fragrance", "flavor"}
TOP_N = 10


def rank_row(site, pid, root, rank=None):
    p = site.products[pid]
    brand = site.brands[p["brand_id"]]["name"]
    c = site.counts(pid, site.product_ingredients(pid))
    pct = round(100 * c["clear"] / (c["n"] or 1))
    num = f'<span class="rank">{rank}</span>' if rank else ""
    return f'''<li class="rank-row">{num}<a href="{root}lipsticks/{pid}/" class="rank-body">
  <span class="eyebrow">{e(brand)} · {e(CATEGORY.get(p["category"], p["category"]))}</span>
  <span class="card-title">{e(p["name"])}</span>
  <span class="muted">{c["clear"]} of {c["n"]} ingredients ({pct}%) have full research with no concerns found</span>
  {bar(c)}
  {legend(c)}
</a></li>'''


def top_lists(site):
    root = "../"
    pids = [pid for pid in site.products if site.lists[pid]]
    info = {}
    for pid in pids:
        ids = site.product_ingredients(pid)
        c = site.counts(pid, ids)
        info[pid] = (c, ids)
    # Ranked by research coverage: the share of the formula with full research and no concerns
    # found. Ties: fewer ingredients worth a closer look, then more ingredients researched.
    ranked = sorted(pids, key=lambda pid: (-info[pid][0]["clear"] / (info[pid][0]["n"] or 1),
                                           info[pid][0]["look"], -info[pid][0]["clear"], site.products[pid]["name"]))
    best = "".join(rank_row(site, pid, root, i + 1) for i, pid in enumerate(ranked[:TOP_N]))

    def fact_list(title, intro, chosen, empty):
        rows = "".join(rank_row(site, pid, root) for pid in sorted(chosen, key=lambda x: full_name(site, x).lower()))
        inner = f'<ul class="rank-list">{rows}</ul>' if chosen else f'<p class="muted">{empty}</p>'
        return f'''<section class="stack">
  <h2>{title} <span class="muted count">({len(chosen)})</span></h2>
  <p>{intro}</p>
  {inner}
</section>'''

    no_flag = [pid for pid in pids if info[pid][0]["look"] == 0]
    no_scent = [pid for pid in pids if not SCENT_IDS & set(info[pid][1])]
    all_clear = [pid for pid in pids if info[pid][0]["clear"] == info[pid][0]["n"]]
    body = f'''<article class="stack">
<h1>Top lists</h1>
<p class="lede">These lists are built automatically from the ingredient ratings and the printed labels. They show how well each formula's ingredients have been researched and what is on the label. They are not safety rankings, and no product is called safe or unsafe.</p>
<p class="muted">No brand pays to appear on or be left off a list. Lists cover every shade label we captured for a product. Ingredient lists can change: always check the label on your product.</p>
<section class="stack">
  <h2>Best-researched formulas</h2>
  <p>Ranked by the share of each product's ingredients that have a full safety report or regulator approval with no concerns found, for both skin contact and swallowing. A lower place usually means some ingredients have not been researched yet, which is a gap in the evidence, not a sign of harm. Ties go to the product with fewer ingredients worth a closer look.</p>
  <ol class="rank-list">{best}</ol>
</section>
{fact_list("No ingredient worth a closer look", "None of the ingredients on these products' labels is currently rated Evidence of harm, Known allergen or Unclear. Some ingredients may not be researched yet.", no_flag, "Every product currently has at least one ingredient worth a closer look.")}
{fact_list("No added fragrance or flavor on the label", "None of these products' labels lists fragrance (parfum) or flavor (aroma). Individual scent chemicals such as limonene or vanillin can still appear, and are shown on each product page.", no_scent, "Every product lists fragrance or flavor.")}
{fact_list("Every ingredient researched, no concerns found", "Every ingredient on these products' labels has a full safety report or regulator approval with no concerns found.", all_clear, "No product reaches this yet. As more research is added, products will appear here.")}
<p class="muted"><a href="{root}how-we-rate/">How we rate</a> · <a href="{root}about/">About and disclaimer</a></p>
</article>'''
    return page(f"Top lists · {SITE}", root, body, "Lipsticks ranked by how well their ingredients are researched, plus label-based lists.")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(data_dir, out_dir):
    site = Site(data_dir)
    if out_dir.exists():
        if not (out_dir / ".lipledger").exists():
            raise SystemExit(f"{out_dir} exists and was not made by this script; refusing to overwrite it.")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    write(out_dir / ".lipledger", "Generated by scripts/build_site.py. Do not edit by hand.\n")
    write(out_dir / ".nojekyll", "")
    write(out_dir / "assets" / "style.css", CSS.strip() + "\n")
    write(out_dir / "assets" / "site.js", JS.strip() + "\n")
    write(out_dir / "index.html", home(site))
    pages = 1
    for pid in site.products:
        if site.lists[pid]:
            write(out_dir / "lipsticks" / pid / "index.html", product_page(site, pid))
            pages += 1
    write(out_dir / "ingredients" / "index.html", ingredients_index(site))
    for iid in site.ings:
        if site.used_in[iid]:
            write(out_dir / "ingredients" / iid / "index.html", ingredient_page(site, iid))
            pages += 1
    write(out_dir / "how-we-rate" / "index.html", how_page())
    write(out_dir / "about" / "index.html", about_page())
    write(out_dir / "top-lists" / "index.html", top_lists(site))
    return pages + 4


def main():
    base = Path(__file__).resolve().parent.parent
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else base / "data"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else base / "docs"
    n = build(data_dir, out_dir)
    print(f"Built {n} pages into {out_dir}")


if __name__ == "__main__":
    main()
