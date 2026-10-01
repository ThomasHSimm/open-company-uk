# Presenter notes and sources: "UK company accounts, made analysable"

Companion to `companies-house-accounts.pptx` (16 slides). Each slide also has speaker notes in the
file. This document collects the figures, where they came from, how confident I am in each, and
some extra material that did not fit on the slides.

---

## Figures used, with source and confidence

**Confidence key:**

- **High:** official or primary source.
- **Medium:** reputable secondary source.
- **Low:** estimate or unverified secondary source. Check these before quoting.

| Figure | Slide | Source | Confidence |
|---|---|---|---|
| 5.48m companies on the register (31 March 2026) | 3 | Companies House annual report 2025/26 (GOV.UK) | High |
| 14.6bn register accesses in 2025/26 (16.3bn in 2024/25) | 3 | Companies House annual report 2025/26 | High |
| 14.7m filings accepted in 2024/25 (13.5m digital) | 3 | Companies House annual report 2024/25 | High |
| £1–3bn annual value to users | 3 | 2019 study commissioned by Companies House and BEIS (GOV.UK news story) | High (as a study estimate) |
| £170–460m/yr value to anti-money-laundering (AML) regulated businesses; about £2,600 per law-enforcement user | 3, 5 notes | 2024 "Value of corporate transparency in tackling crime", cited in DBT/Companies House release, June 2025 | High (as a study estimate) |
| Free accesses grew from 1.3bn (2015/16) to 16bn+ (2023/24) | 3 notes | Companies House blog, June 2025 | High |
| Officers bulk data provided on request only | 4 | CH Guide (chguide.co.uk); Companies House developer forum | Medium |
| REST API limit of about 600 requests per 5 minutes | 4 notes | My understanding of the CH developer docs; not re-checked | Medium–low |
| Creditsafe and D&B sell through G-Cloud | 5 | Digital Marketplace listings (Creditsafe; D&B Risk Analytics G-Cloud 14 terms) | High |
| Commercial Credit Data Sharing (CCDS): designated banks share with Experian, Equifax and Creditsafe; D&B designated in 2019 | 7 | HM Treasury CCDS consultation (GOV.UK); BIIA | High |
| CCJ searches from about £10 | 7 | Registry Trust TrustOnline page | High |
| HM Land Registry company-ownership datasets free since November 2017 (account and licence required) | 6 | HMLR blog (2017); Use land and property data service | High |
| Creditsafe prices: ~£5–15 per UK report; small teams ~$200–600/month; enterprise ~$15k–75k+/yr | 8 | Vendr buyer guide (transaction data) | Medium |
| D&B £245/yr | 8 | iwoca guide. This is for your **own** credit file (Credit Insights), not buying data about others | Medium |
| Experian ~£30/month | 8 | Rise Funding guide. This is for your **own** business profile | Medium |
| FAME ~£31k–75k/yr for 5–20 users | 8 | businessdataguide.com comparison. The source itself says to verify it | **Low** |
| Beauhurst "five figures a year" | 8 | My guess; no public price | **Low** |
| DataLedger datasets from £295 | 8 | DataLedger site | High (their own price) |
| Size thresholds from 6 April 2025 | 10 | Lexology summary; same figures used in the project explainer | High |
| ECCTA accounts changes confirmed for April 2028 | 11 | ICAEW, June 2026 | High (as of June 2026; may change again) |
| Credit agencies estimate turnover from balance sheets | 10, 11 | Creditsafe's published "Estimated Turnover Indicator" description | High |
| iXBRL adoption about 0% (2010) to about 97% (2014) | 11, 15 | Project's live check of the bulk product | High (project measurement) |
| 152 months, 2014-01 to 2026-08; about 2.0bn facts; 4,455 concepts | 12, 13 | Project backfill and inventory | High (project measurement) |
| Restatement 7.93% vs 7.94% (2022–23); 9.36% (2014–2026) | 12, 15 | Project out-of-core engine vs panel check | High (project measurement) |
| WIDE about 33.5m rows (as first reported), 36.7m (latest); 2.6 GB; LONG 9.2 GB | 13 | Project pivot and Kaggle staging | High (project measurement) |
| Creditors genuine total about 4% of company-periods | 14 notes | Two-archive production sample | Medium (sample-based) |
| Employee facts tagged in GBP: about 29%, median value 1 | 14 notes | Project full-scale check | High (project measurement) |

---

## The GIS comparison (slide 9): what the evidence supports

**The claim:** "Most of the data is open; vendors mainly sell packaging."

**What the evidence supports:**

- **True for describing companies.** Filed financials, officers, ownership and property ownership
  all come from free registers. Much of what research platforms and low-cost tools sell is
  cleaning, history, linking and an interface.
- **Not true for predicting non-payment.** The best credit scores rely on data that is not public:
  - bank credit data shared under the CCDS scheme with only four designated agencies
  - trade payment histories collected from suppliers
  - county court judgment (CCJ) feeds, which are paid
- **Fair wording:** "most, not all". The private layer is small in volume but carries much of the
  predictive value.

**What I could not find quickly:** the total amount the civil service spends on company data. If
you want a slide with a figure like your GIS analysis, that would need a proper search of
Contracts Finder, G-Cloud award data and departmental spend-over-£25k files for Creditsafe, D&B,
Experian, Equifax and Moody's/BvD. Any single figure is an estimate until that search is done.

---

## Possible extra slides (not included)

1. **A worked example.** Show one real company's balance sheet over time, the same figure appearing
   twice because of a restatement, and the as-first-reported vs latest values. This is often the
   clearest demonstration for data audiences. Pick a company without a sole director.
2. **Joining sources.** Show one company number linked across Basic Company Data, accounts, PSC,
   HMLR ownership and the Gazette.
3. **A live demo** of the Kaggle starter notebook.
4. **Government spend:** only after the search described above.

---

## Things to check before presenting

- Add the Kaggle links to slides 13 and 16 once the datasets are published.
- Check the ECCTA April 2028 date again, because it has already moved once.
- Mark the FAME and Beauhurst prices as low confidence out loud, or remove them.
- The code on slide 14 uses the example number `00012345`. Replace it with a real company for a
  demo.

---

## Evidence for slide 12: open tools vs this pipeline

Reproduce it with `tool-comparison-check.py`, which records its setup in its header.

**Sample:** 379 real Companies House filings from the ONS Big Data repository:

- 205 iXBRL and 174 plain XML
- made-up dates from 2016 to 2018
- hand-picked by ONS, not random

| Tool | Result |
|---|---|
| ixbrlparse 0.11.2 | Parsed 205/205 iXBRL files and 174/174 XML files. It read all 202 dash figures as 0 and handled all 363 `sign="-"` figures correctly. It exposed 1,679 dimensional facts and ran at about 33 ms per iXBRL file |
| ixbrl-parse 0.11.0 | Parsed 101/205 files. The failures were 89 ValueErrors, caused by unit names without a namespace prefix, and 15 KeyErrors that I did not diagnose |
| Arelle 2.45.3 | Not tested for values. It needs the FRC taxonomy files, and this sandbox can't download them. Offline, it returns concept names without values |

**What stays with the pipeline in this sample:**

- **Repeated figures:** 164 concept/context pairs appear more than once, and none of them disagree.
- **Creditors:** 99 of the 107 filings that report Creditors give only its parts, with no total.

**Conclusion:** single-filing parsing is solved, and ixbrlparse does it well. Our pipeline adds these
things on top:

- full-history bulk orchestration
- deduplication
- rules for totals versus components
- cross-filing restatement handling and point-in-time provenance
- accounting invariants
- a published 2014–2026 table

Someone could build the same thing on ixbrlparse. The parsing isn't the hard part.

**Two admissions:**

1. Our pipeline first treated dashes as missing, and we fixed that later. ixbrlparse handles them
   correctly by default.
2. ixbrlparse reads plain-XML filings, and our extractor skips them.

**Action before presenting:** ask the agent to report the number of XML files skipped for each year
from 2014 to 2026, using the manifest. If the share of XML is material in the early years, our
2014–2018 coverage is lower than it looks. In that case, either add XML parsing or state the gap on
the limitations slide.

**Existing datasets:**

- The CorpSignals Kaggle dataset ("up to 2023") comes from a lead-generation vendor, and I couldn't
  inspect its contents. Open it while logged in to Kaggle and check which years it covers and how
  it handles restatements.
- DataLedger (paid) describes its financials as current year plus prior year for each company.

---

## Slides 6–7: other UK data and prior work (added)

**Slide 6** puts the sources in priority order for this repo. Each one joins to Companies House,
mostly on the company number.

**Checked:**

- The Gazette has a free official API.
- HM Land Registry's company-ownership data is free and keyed by company number. Past files are
  available through its API, and its licence doesn't allow republishing.
- Payment practices: every report can be downloaded, and each has the company number and
  days-to-pay fields.
- The FCA API allows about 10 requests per 10 seconds.

**Estimated:** how well contracts and charity records match to company numbers.

**Slide 7** covers prior work. Everything on it has a source:

- **Global Witness and DataKind UK**, "The Companies We Keep" (2018). Their code is public. They
  matched people using a combination of name, month and year of birth, and address. Compare this
  with our PSC matching.
- **Private Eye** (2015), then **Who Owns England**, then **TaxPolicy.org.uk** (January 2026). The
  2026 work cross-checked Land Registry records against the overseas entities register and
  published its method.
- **Transparency International UK**, "Track and Trace" and "Behind the Masks". They found £15.3bn
  of high-risk Covid contracts, and one of their red flags was suppliers that were only weeks old.
- **Open Ownership**, whose `bods-uk-psc-pipeline` publishes UK ownership data in a standard format.
  They have combined it with procurement data (in the Open Contracting format) and with
  OpenSanctions data (in its FollowTheMoney format).
- **OpenSanctions**, whose `gb-coh-psc` (now part of `opensanctions/graph`) converts Companies
  House ownership data.
- **David Kane / 360Giving**, with Find that Charity: 16 sources and about 660,000 non-profits.
- **Academic research:**
  - A systematic review of 145 studies on predicting small-company default found nearly half used
    commercial data services.
  - A 2024 study of 8,490 UK charitable companies found they file later when in financial
    difficulty.

**Judgement, not measured:** "most projects are one-off investigations".

**Corrected on the slide:** a company-age flag is suggested as a flag to add. I haven't confirmed the
repo already has one.

---

## Version 2 update: final measured figures

These replace the earlier estimates on slides 13, 14 and 17. Source: `docs/accounts-parser-check.md`.

| Figure | Final |
|---|---|
| Speed per filing (ours / ixbrlparse / Arelle) | 0.65 ms / 7.7 ms / about 1 s |
| Full archive of 35.8 million filings on 8 cores | Ours about 2 h; ixbrlparse about 1.4 days; Arelle about 95 days |
| Numeric agreement, ours vs ixbrlparse (dashes excluded) | 99.999% |
| Filings recovered by the prefix fix | **61,085**, measured directly. The ~292,000 estimate was wrong because it came from stale scan files |
| Values corrected (European decimal formats) | 1,096 |
| Values un-blanked (the `num-dot-decimal` spelling) | 540, in 3 months |
| Plain-XML filings added (through ixbrlparse) | About 273,000 |
| Regressions | 0 |
| Restatement rate | 9.36%, unchanged |
| Concepts in LONG | 4,593 |
| Still skipped by design | Contexts with two or more breakdowns (25.3% of filings contain some) and custom breakdowns (20.1%); about 38% of filings combined |
