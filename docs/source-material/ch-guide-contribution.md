# Draft contribution for CH Guide — accounts bulk data pitfalls

**For the maintainer. Do not submit as-is.** This is a neutral draft of a possible contribution to
[CH Guide](https://chguide.co.uk/)'s accounts page, offered because that page documents the
accounts bulk product's *mechanics* well but does not yet cover the *parsing pitfalls* that only
surface at scale. Everything below is drawn from this project's own measurements
(`docs/accounts-*.md`, `docs/source-material/deck-corrections.md`); figures are included so a
reader can judge materiality. Review the tone, trim to fit CH Guide's style, and confirm each
figure before sending.

---

## Suggested addition: reading the tagged figures

The accounts bulk data is tagged inline XBRL (iXBRL): ordinary HTML accounts in which each figure
carries a machine-readable tag, for example `<ix:nonFraction name="Equity" unitRef="GBP">12,968`.
Reading a single filing is well supported by existing libraries. A handful of issues only appear
when parsing the whole archive, and each can give wrong numbers that look correct:

- **A dash means nil, not missing.** UK accounts print "–" for a nil value. Treat it as 0, not as
  a missing value — reading it as missing lets a later filing's comparative silently back-fill the
  cell.
- **Scale and sign.** A numeric tag's `format` and `sign` attributes change magnitude and
  direction. European decimal formats (`numdotcomma` and relatives) write `4.506` to mean 4,506;
  read naively, that is wrong by ~1,000×.
- **Namespace prefixes.** iXBRL tags live in a namespace a filing may bind to any prefix. Matching
  a single hardcoded prefix (e.g. `ix:`) silently drops every filing that uses another binding —
  the filing extracts zero facts with no error.
- **Restatements in comparatives.** Each filing carries the current year and a prior-year
  comparative, so the same (company, period, concept) appears in more than one filing, and the two
  values do not always agree. For point-in-time work, keep the first-reported value, not a later
  comparative.
- **The plain-XML share over time.** A minority of filings are plain XBRL (`.xml`), not iXBRL
  (`.html`). The XML share is higher in the early years, so an iXBRL-only reader understates early
  coverage.

A worked, measured write-up of each — with archive-wide counts and how they were checked against
two independent parsers (`ixbrlparse` and Arelle) — is maintained in the open-company-uk project:
<https://github.com/ThomasHSimm/open-company-uk> (see `docs/site/guide/pitfalls.qmd` and
`docs/accounts-validation-summary.md`).

---

*Offered under the same open spirit as CH Guide; attribution to open-company-uk appreciated but
not required.*
