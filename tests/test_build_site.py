"""Build the site from the real data and check the pages it must always have."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_site  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "site"
    build_site.build(ROOT / "data", out)
    pages = list(out.rglob("*.html"))
    assert len(pages) > 10, pages
    for p in pages:
        text = p.read_text()
        assert "For information only." in text, p
        assert "toxicologist" in text, p
        assert "not medical, safety or legal advice" in text, p
    mac = (out / "lipsticks" / "mac-macximal-silky-matte-lipstick" / "index.html").read_text()
    assert "of 34</span> ingredients: no concerns found" in mac
    assert "../../ingredients/titanium-dioxide/" in mac
    tio2 = (out / "ingredients" / "titanium-dioxide" / "index.html").read_text()
    assert "Not counted" in tio2  # the SCCS summary is shown but does not count
    assert "In lip products:" in tio2 and "t-u" in tio2
    # No product-level verdicts.
    for word in ("non-toxic", "this product is safe", "this lipstick is safe", "is toxic"):
        assert word not in mac.lower(), word
    top = (out / "top-lists" / "index.html").read_text()
    assert "Best-researched formulas" in top and "not safety rankings" in top
    assert top.count('class="rank"') == build_site.TOP_N
    for word in ("safest", "non-toxic", "cleanest", "is toxic"):
        assert word not in top.lower(), word
    # SPF lip products: own section on the home page, actives marked on the product page.
    home = (out / "index.html").read_text()
    assert 'id="spf"' in home and "supergoop-play-lip-balm" in home
    play = (out / "lipsticks" / "supergoop-play-lip-balm" / "index.html").read_text()
    assert "Active ingredients:</strong> Avobenzone (3%)" in play and 'class="act"' in play
    for word in ("non-toxic", "this product is safe", "is toxic", "stop using sunscreen"):
        assert word not in play.lower(), word
    how = (out / "how-we-rate" / "index.html").read_text()
    assert 'id="spf"' in how and "does not represent a conclusion" in how
    # Refuses to wipe a folder it did not create.
    other = Path(tmp) / "other"
    other.mkdir()
    try:
        build_site.build(ROOT / "data", other)
        raise AssertionError("should refuse")
    except SystemExit:
        pass
print("OK: site build tests passed")
