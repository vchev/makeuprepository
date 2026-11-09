# Makeup Ingredient Facts

An evidence-based guide to "toxic" and "non-toxic" makeup ingredients and brands. Each page separates hazard from real-world exposure risk and cites primary research and regulatory sources.

## Publish with GitHub Pages

1. In the repository, go to **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**, branch `main`, folder `/ (root)`, and save.
3. The site appears at https://vchev.github.io/makeuprepository/ within a few minutes.

## Edit content

- Ingredient pages live in `_ingredients/`. Copy an existing file to start a new one; the fields at the top (between the `---` lines) fill in the verdict box and fact cards.
- Other pages (`index.md`, `start-here.md`, `myth-checks.md`, `brands.md`, `methodology.md`) are plain Markdown.
- Update `reviewed:` on an ingredient page whenever you re-check its sources.

## Preview locally

```sh
gem install jekyll
jekyll serve --baseurl /makeuprepository
```

Then open http://localhost:4000/makeuprepository/.
