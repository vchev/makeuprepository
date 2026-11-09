# The Lip Ledger

What the research says about the ingredients in popular lipsticks. Every ingredient is rated for skin contact and swallowing, using only full safety reports and regulations, by fixed automatic rules. The site rates ingredients, never products, and is for information only.

## How it fits together

- `data/` is the database: products, labels, ingredients, sources, findings and regulations (see `data/README.md`).
- `scripts/rate.py` checks the data and applies the rating rules.
- `scripts/build_site.py` turns the database into the website in `docs/`. Never edit `docs/` by hand; rebuild it.

## Update the site

```sh
python3 scripts/rate.py          # check the data and regenerate ratings
python3 scripts/build_site.py    # rebuild docs/
python3 tests/test_rate.py && python3 tests/test_build_site.py
```

Commit the changes to `data/` and `docs/` together.

## Publish with GitHub Pages

1. In the repository, go to **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**, branch `main`, folder `/docs`, and save.
3. The site appears at `https://<owner>.github.io/<repository>/` within a few minutes.

## Preview locally

```sh
cd docs && python3 -m http.server 8000
```

Then open http://localhost:8000/.
