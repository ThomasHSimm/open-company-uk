# Site restructure — what moved where

This logs the content moves in the `site_restruct` branch rebuild of `docs/site/`, so nothing is
lost. The old site was five pages presenting the repo only as an indicators pipeline; the new site
is a hub with a navbar of **Home · Guide · Datasets · Indicators · Landscape · Evidence ·
Reference**. No code under `src/`, `scripts/` or `tests/` was changed.

## Pages moved or superseded

| Old file | New location | Change |
|---|---|---|
| `index.qmd` | `index.qmd` (rewritten) | Now a hub with the opening line "UK company data: explained, connected, usable", three entry cards (Guide / Datasets / Indicators), and a "Start here" path for analyst / developer / researcher. Keeps the not-a-rating-product, no-composite-score and OGL statements. |
| `methodology.qmd` | `indicators/methodology.qmd` | Content preserved; a plain-language **Summary** added at top. The two links to the generated docs changed from relative `../rules.md` / `../data-dictionary.md` (which pointed outside the site project and would break on render) to GitHub `blob/main` URLs — see "Deviations" below. |
| `validation.qmd` | `indicators/validation.qmd` | Content preserved; Summary added. "Results pending" box unchanged. |
| `limitations.qmd` | `indicators/limitations.qmd` | Content preserved; Summary added. |
| `accounts.qmd` | **Superseded** by `datasets/accounts.qmd` (the dataset) and `guide/accounts-data.qmd` (what the accounts data is) | Content expanded, not lost. The restatement figure was updated from 9.27% to **9.36%** to match the latest measurement (`docs/accounts-limitations.md` dash-nil-fix section and `kaggle-v2/README.md`); the old 9.27% was the pre-dash-fix value. |

## New pages, and their source material

| New page | Built from |
|---|---|
| `guide/companies-house.qmd` | Deck slides 3–4 + notes; links to CH Guide for mechanics |
| `guide/sources-map.qmd` (main new page) | Deck slides 6–8 + slide 18 notes; `docs/plan.md`; `literature/open-company-uk-source-queue-2026-08.md` |
| `guide/accounts-data.qmd` | Deck slides 11–12; `docs/source-material/accounts-explainer.html`; `docs/accounts-limitations.md` |
| `guide/pitfalls.qmd` | Deck slide 13; `docs/accounts-*.md`; `docs/recon-psc*.md`; `docs/source-material/deck-corrections.md` |
| `datasets/accounts.qmd` | Deck slides 15–17; `kaggle-v2/README.md`, `kaggle-v2/column-dictionary.md`; `docs/accounts-limitations.md`; `kaggle-long-v2/README.md` |
| `datasets/accounts-validation.qmd` | `docs/accounts-validation-summary.md`; deck slides 12–14; `docs/source-material/tool-comparison-check.py`, `compare-ours-vs-ixbrlparse.py` |
| `datasets/psc.qmd` | `docs/recon-psc.md`, `docs/recon-psc-results.md`; deck slides 17–18 notes |
| `indicators/non-compliance.qmd` | New placeholder (Planned); `docs/plan.md` phase 1.2 |
| `landscape/who-uses.qmd` | Deck slide 5 + notes |
| `landscape/market.qmd` | Deck slides 8–10 + notes |
| `evidence/prior-work.qmd` | Deck slide 7 + notes; `literature/open-company-uk-source-queue-2026-08.md` |
| `evidence/register.qmd` | `literature/open-uk-company-research-pack.md` §4 (schema); the source queue. Structure only — the populated register is to come. |
| `reference.qmd` | Links to generated `rules.md`, `data-dictionary.md`, `AUDIT.md`, accounts/PSC docs, source material, and the repo |

## Source material staged into `docs/source-material/`

The maintainer had left the deck and its companions in `~/Downloads`; the text-based ones were
copied into `docs/source-material/` so the repo is self-contained (the binary `.pptx` was **not**
copied, per the text-only constraint — its text was extracted instead):

- `companies-house-accounts-notes.md` — presenter notes with figures, sources and confidence (the latest, formerly `…-notes(2).md`)
- `companies-house-accounts-deck.md` — slide + speaker-note text extracted from `…(3).pptx` with a stdlib reader
- `accounts-explainer.html` — the original richer accounts explainer (formerly `index.html`)
- `tool-comparison-check.py`, `compare-ours-vs-ixbrlparse.py` — the parser-comparison scripts
- `deck-corrections.md` — already present; measured corrections for the deck

## Deviations flagged

- **`_quarto.yml`** retitled from "open-company-uk methodology" to "open-company-uk" and given
  dropdown menus, a GitHub link, a page footer (OGL / not-affiliated), and the `cosmo` theme.
- **Two link targets changed** in `indicators/methodology.qmd` (the generated-doc links), as noted
  above, to avoid broken links on render. This is the only edit to otherwise-moved content.
- Four old top-level pages (`methodology`, `validation`, `limitations`, `accounts`) were
  `git rm`-ed after their content was moved/superseded.
