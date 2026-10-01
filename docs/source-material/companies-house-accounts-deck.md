# Companies House accounts deck — extracted text

Text and speaker notes extracted from `companies-house-accounts.pptx` (the "UK company
accounts, made analysable" deck, 18 slides). Extracted with a stdlib-only reader
(`zipfile` + ElementTree over the slide/notes XML) because `python-pptx`/`markitdown` were
not installed; the original `.pptx` is a binary and was not copied into the repo under the
text-only build constraint. Companion figures, sources and confidence levels are in
`companies-house-accounts-notes.md`; measured corrections are in `deck-corrections.md`.

This file is reference material for the site build, not a published page.


======================================================================
SLIDE 1  (ppt/slides/slide1.xml)
======================================================================
  UK company accounts,
  made analysable
  Companies House data, the market built on it, and an open 2014–2026 accounts dataset for analysts
  open-company-uk  ·  Thomas Simm  ·  2026
  --- NOTES ---
    > PURPOSE: A practical tour for data scientists and analysts who might use UK company data. The first half is about the landscape: what Companies House publishes, who uses it, what else exists in the UK, and what the commercial market charges. The second half is about one dataset: the annual accounts, and the open, analysis-ready version this project built.

FRAMING TO SET UP EARLY: most UK company data starts as free public data. The commercial market mostly sells convenience, history, linking and scores, plus a few genuinely private data sources. That has implications for what an analyst can build for free.

All figures in this deck are sourced in the separate notes file. Commercial prices are indicative only.

======================================================================
SLIDE 2  (ppt/slides/slide2.xml)
======================================================================
  ROADMAP
  What we'll cover
  1
  Companies House
  what it is and what it publishes
  2
  Who uses it
  government, credit agencies, business
  3
  Other UK sources
  free registers and harder-to-get data
  4
  The market
  who packages the data, and indicative costs
  5
  Accounts data
  what it is, who files what, what's changing
  6
  What we built
  extracting 12 years of filings
  7
  Using the dataset
  structure, how to use it, limitations
  2
  --- NOTES ---
    > Sections 1–4 are the landscape; sections 5–7 are the accounts dataset.

If time is short, sections 3 and 4 can be compressed to one slide each; the core for a technical audience is 1, 5, 6 and 7.

======================================================================
SLIDE 3  (ppt/slides/slide3.xml)
======================================================================
  1 · COMPANIES HOUSE
  The UK's register of companies
  Executive agency of the Department for Business and Trade.
  Incorporates and dissolves companies, records their filings, and publishes them.
  Register data has been free to search and download since 2015.
  Reforms under the Economic Crime and Corporate Transparency Act 2023 (ECCTA) are turning it from a passive record into a register that checks identities and data quality.
  5.48m
  companies on the register
  (31 March 2026)
  14.6bn
  times register data was
  accessed in 2025/26
  14.7m
  filings accepted in 2024/25
  (13.5m digitally)
  £1–3bn
  estimated annual value
  to users (2019 study)
  3
  --- NOTES ---
    > KEY POINTS
- Companies House is the registrar for companies across England & Wales, Scotland and Northern Ireland. It registers what companies file; historically it did very little checking of that information. ECCTA 2023 gave it new powers: identity verification for directors and people with significant control, the ability to query and reject information, and data-sharing with law enforcement.
- Free access since 2015 changed the market. Use grew from 1.3 billion free accesses in 2015/16 to over 16 billion in 2023/24. The 2025/26 annual report gives 14.6 billion accesses (down from 16.3 billion in 2024/25) and a register of 5.48 million companies.
- Value: a 2019 study commissioned by Companies House and BEIS put user benefits at £1–3 billion a year. A 2024 study put the value of register information to anti-money-laundering (AML) regulated businesses at £170–460 million a year.

SOURCES: Companies House annual report and accounts 2024/25 and 2025/26 (GOV.UK); "Companies House celebrates 10 years of open data" (June 2025); "New report estimates value of Companies House data at up to £3 billion per year" (GOV.UK, 2019).

======================================================================
SLIDE 4  (ppt/slides/slide4.xml)
======================================================================
  1 · COMPANIES HOUSE
  What Companies House publishes, and how to get it
  Source
  What's in it
  Format & frequency
  Watch out for
  Basic Company Data
  Live companies: name, number, status, registered office, SIC codes, key dates
  CSV, monthly
  Live companies only; no history
  Accounts bulk data
  Electronically filed annual accounts, tagged figure by figure
  iXBRL/XML in ZIPs; daily and monthly, back to 2008
  E-filed only; mostly balance sheets
  PSC snapshot
  People and entities with significant control, plus statements
  JSON, daily
  Only today's file is served; keep your own copies
  Officers bulk
  Directors and secretaries
  On request only
  Not a public bulk download
  APIs
  REST: profiles, officers, PSC, filings, charges, insolvency. Streaming: live changes. Document API: filed documents
  JSON; free key; rate-limited
  No parsed financial figures; no bulk history
  4
  --- NOTES ---
    > THE THREE BULK PRODUCTS plus the APIs are the core. Most analysts need only these.

- Basic Company Data: a monthly CSV snapshot of live companies. Useful as a spine for joins: company number, name, status, SIC codes, incorporation date and accounts due dates. It does not contain dissolved companies or history, so reconstructing past states means keeping your own monthly copies.
- Accounts bulk data: the annual accounts that companies filed electronically, as individual iXBRL (HTML with embedded tags) or XML files in daily and monthly ZIPs, with history back to 2008. This is the focus of the second half of the talk.
- PSC snapshot: persons with significant control (PSCs), as newline-delimited JSON, published daily. Our recon found ceased records are retained, so control history back to April 2016 is reconstructable. But only the current day's file is published, so corrections over time are lost unless you archive snapshots yourself.
- Officers: there is an officers bulk product, but it is provided on request rather than as a public download.
- APIs: the REST API returns profiles, officers, PSCs, filing history, charges and insolvency data per company. The Streaming API pushes changes in near real time. The Document API returns the filed documents themselves. The API does NOT return parsed financial figures; to get numbers you must download and parse the iXBRL, which is exactly what this project does at scale. My understanding is the REST API limit is about 600 requests per 5 minutes per key; check the current developer documentation.

SOURCES: CH Guide (chguide.co.uk) bulk data pages; Companies House download pages; Companies House developer forum (officers bulk on request).

======================================================================
SLIDE 5  (ppt/slides/slide5.xml)
======================================================================
  2 · WHO USES IT
  Government and business both depend on it
  Public sector
  Procurement: buyers check suppliers' economic and financial standing, often through credit agencies
  Law enforcement, HMRC and the Insolvency Service in investigations and director cases
  Official statistics and business registers
  Local authorities checking suppliers and local businesses
  Business and others
  Credit agencies and data providers: the raw material for their products
  Lenders and suppliers deciding credit terms
  Anti-money-laundering and know-your-customer checks
  Sales prospecting, investors, researchers and journalists
  Government often buys this data back as a packaged product: Creditsafe and Dun & Bradstreet both sell to the public sector through G-Cloud.
  5
  --- NOTES ---
    > Companies House's own research identifies three user types: direct users (companies, creditors, investors and researchers), intermediaries (credit reference agencies and other data providers that use the data as an input), and providers of public goods (government departments and law enforcement).

PUBLIC SECTOR EXAMPLES
- Procurement: Cabinet Office guidance on assessing suppliers' economic and financial standing (EFS) expects buyers to check the financial health of bidders and monitor it during contracts. In practice, this often means buying credit agency reports rather than reading raw filings.
- Law enforcement: the 2024 "value of corporate transparency in tackling crime" study estimated register value at around £2,600 per law-enforcement user per year.
- Insolvency Service: director conduct and disqualification work draws on company filings.
- Statistics: the official business register used by ONS draws on administrative sources. I have presented this generally rather than claim specific data flows.

THE INTERESTING POINT: the same public data flows out for free, then gets bought back by the public sector as a packaged, scored product. Both Creditsafe and Dun & Bradstreet list services on the government's G-Cloud Digital Marketplace. That mirrors the pattern in the GIS market, where most underlying data is open and much of the spend is on software and convenience. Slide 10 comes back to how far that analogy holds.

SOURCES: GOV.UK 2019 value report (user types); Wired-Gov / DBT release June 2025 (AML and law-enforcement values); GOV.UK "Assessing and monitoring the Economic and Financial Standing of Suppliers" guidance note; Digital Marketplace G-Cloud listings for Creditsafe and D&B Risk Analytics.

======================================================================
SLIDE 6  (ppt/slides/slide6.xml)
======================================================================
  3 · OTHER UK SOURCES
  Other UK data that joins to Companies House
  Source
  What it adds
  Company no.?
  Access and licence
  Use in this project
  The Gazette
  Winding-up petitions, insolvencies, strike-offs, with dates
  Yes
  Free official API (JSON), paged
  Outcome labels; how early signals appear
  HM Land Registry
  UK and overseas companies owning property in England & Wales
  Yes
  Free monthly CSV, history via API. No republishing
  Asset ownership; overseas owners
  Payment practices
  Large firms: days to pay, % paid late, terms
  Yes
  All reports downloadable
  Open stand-in for payment behaviour
  Contracts Finder / Find a Tender
  Public contracts and winning suppliers
  Sometimes
  Bulk, open contracting standard
  Public-sector exposure; very new suppliers
  Charity registers
  Charitable companies: finances, trustees
  Mostly
  Bulk downloads
  Non-profit segment
  Overseas entities register
  Foreign owners of UK property and their owners
  Own ID; links to HMLR
  Companies House, free
  Ownership beyond the UK
  FCA register
  Authorised financial firms
  Partly
  API only, ~10 requests per 10s
  Flag regulated firms
  Rows are in suggested priority order. Most are free; the catch is licences and matching, not price.
  6

======================================================================
SLIDE 7  (ppt/slides/slide7.xml)
======================================================================
  3 · OTHER UK SOURCES
  Who has used this data before, and how
  Global Witness + DataKind UK
  PSC register, 2018. Graph database, open notebooks. Matched people on name + birth month/year + address.
  Private Eye → TaxPolicy.org.uk
  Land Registry offshore ownership, 2015–2026. The 2026 map cross-checks the overseas entities register; method published.
  Transparency International UK
  Covid contracts, 2021–25. Red flags included suppliers only weeks old, using incorporation dates.
  Open Ownership + OpenSanctions
  Open pipelines turning UK PSC data into standard formats; combined with procurement and sanctions.
  David Kane / 360Giving
  Find that Charity: 16 sources, ~660k non-profits. Also wrote ixbrlparse.
  Academic research
  145 small-firm default studies reviewed: nearly half used paid data services. One study used 8,490 charities' filing dates.
  Common tools: Jupyter and pandas, graph databases (Neo4j), Elasticsearch, linked data (RDF/SPARQL), DuckDB. Most projects are one-off investigations; Open Ownership and OpenSanctions maintain pipelines.
  7
  For us: benchmark our PSC person matching against theirs.
  For us: reuse their Land Registry to overseas-entity method.
  For us: company age is an easy register flag to add.
  For us: reuse their PSC pipelines; add sanctions links.
  For us: charity lookup is already built; reuse it.
  For us: open data fills a real research gap.
  --- NOTES ---
    > This is where the genuine data advantage sits. None of these can be rebuilt from Companies House.

- Commercial Credit Data Sharing (CCDS): under the Small Business, Enterprise and Employment Act 2015, designated banks must share credit information about their small and medium-sized business customers with credit agencies designated by HM Treasury. The original three were Experian, Equifax and Creditsafe; Dun & Bradstreet was added in 2019. Other lenders can access it through those agencies, subject to conditions. This is bank account and borrowing behaviour, which is very predictive and not public.
- Trade payment data: credit agencies collect invoice payment experiences from suppliers and turn them into measures such as days beyond terms or D&B's PAYDEX score. It is proprietary and costly to replicate.
- County court judgments: Registry Trust is the statutory maintainer of the Register of Judgments, Orders and Fines. TrustOnline searches start from about £10 per search, and credit agencies buy bulk data. CCJs are a strong distress signal and are missing from open datasets.
- Full profit and loss for small companies: small companies file a balance-sheet-only version with Companies House, but they give HMRC full accounts with the corporation tax return. That data is confidential.
- ONS and HMRC microdata: available for approved research through secure research services, not for commercial or open use.

IMPLICATION FOR ANALYSTS: an open model built on Companies House data can match commercial products on filed financials and structure, but not on payment behaviour, bank data or judgments. Be honest about that gap.

SOURCES: HM Treasury Commercial Credit Data Sharing consultation (GOV.UK); BIIA note on D&B designation (2019); Registry Trust services and TrustOnline pages.

======================================================================
SLIDE 8  (ppt/slides/slide8.xml)
======================================================================
  3 · OTHER UK SOURCES
  The data you can't easily get
  Bank credit data on small firms
  Shared by designated banks only with four designated credit agencies (Experian, Equifax, Creditsafe, D&B)
  Trade payment behaviour
  Days-beyond-terms and payment scores from credit agencies' own supplier networks. Paid
  County court judgments
  Register of Judgments via Registry Trust. Searches from about £10; bulk licences for credit agencies
  Full profit and loss for small firms
  Filed with HMRC alongside the tax return. Not public
  Official business microdata
  ONS business register extracts. Accredited researchers only, via secure research services
  Tax records
  HMRC Datalab. Approved research projects only
  8
  --- NOTES ---
    > HOW TO READ THIS: the market splits into three groups.
1. Credit reference agencies (Creditsafe, D&B, Experian, Equifax): scores, reports and monitoring for credit and supplier decisions. Their advantage is the private data on the previous slide.
2. Research platforms (Moody's Bureau van Dijk FAME and Orbis, Beauhurst): deep standardised financial histories and ownership trees for analysts, bankers and universities. UK universities typically access FAME through JISC licences.
3. Low-cost and open tools (Endole, Company Check, OpenCorporates, DataLedger): repackaged Companies House data, often freemium.

PRICE CONFIDENCE (be upfront with the audience):
- Creditsafe: from a Vendr buyer guide based on observed transactions. It reports about £5–15 per UK report on pay-per-report, about $200–600 a month for small teams and about $15k–75k+ a year for enterprise contracts. Moderate confidence.
- D&B £245/yr: this is for a company viewing its OWN credit file (Credit Insights), not for buying data about others. Enterprise pricing is by quote.
- Experian about £30/month: again for your own business profile.
- FAME about £31k–75k/yr: from a third-party comparison article that itself flags the figure for verification. Low confidence.
- Beauhurst: no public price; the five-figure estimate is my guess. Low confidence.
- DataLedger: custom datasets from £295 per its own site.

WHY IT MATTERS: an analyst at a small organisation can reproduce much of what the cheaper tools offer from open data. What costs real money is scale, history, linking and the private data.

SOURCES: Vendr Creditsafe buyer guide; iwoca guide (D&B £245); Rise Funding guide (Experian); businessdataguide.com D&B vs FAME comparison; DataLedger site; Digital Marketplace listings.

======================================================================
SLIDE 9  (ppt/slides/slide9.xml)
======================================================================
  4 · THE MARKET
  Who sells company data, and roughly what it costs
  Provider
  What you get
  Indicative cost
  Creditsafe
  Credit reports, scores, monitoring, API
  ~£5–15 per UK report; small teams ~$200–600/month; enterprise ~$15k–75k+/yr
  Dun & Bradstreet
  DUNS entity IDs, risk scores, supplier monitoring
  Own-file insights £245/yr; enterprise by quote
  Experian / Equifax
  Business credit scores, enriched with bank data
  Own profile ~£30/month; enterprise by quote
  Moody's BvD: FAME
  Standardised multi-year financials, ownership trees
  ~£31k–75k/yr for 5–20 users (unverified)
  Beauhurst
  High-growth and investor-backed companies
  Quote only; my guess is five figures a year
  Low-cost / open
  Endole, Company Check, OpenCorporates, DataLedger
  Free tiers; datasets from ~£295
  Indicative only. From third-party price guides and vendor pages. Prices are negotiable and change often; verify before quoting.
  9
  --- NOTES ---
    > THE GIS COMPARISON: in an earlier look at GIS spending in the civil service, most of the underlying geographic data was open, and much of the spend went on software licences (six figures a year per group) that made open data easy to use. Company data follows a similar pattern, with one important difference.

- Bottom layers: open register data plus the work to clean, link and keep history. This is where most vendor effort goes for filed financials and firmographics, and where an open pipeline can compete.
- Private data layer: trade payments, bank credit data from the CCDS scheme, and court judgment feeds. This is not open and cannot be rebuilt. It is why credit agency scores outperform anything built only on filings, so the "it's all open data" claim holds for MOST of the stack, not all of it.
- Top layer: scores, dashboards, alerts, APIs, support and integration into procurement and credit workflows. Buyers often pay for reduced risk and effort here, not for the data itself.

A FAIR CONCLUSION: for describing companies (who they are, what they filed, who controls them), open data plus good engineering gets you most of the way. For predicting who will not pay, the private layer still matters.

======================================================================
SLIDE 10  (ppt/slides/slide10.xml)
======================================================================
  4 · THE MARKET
  Where the value sits
  Scores, UI, alerts, API, support
  Private data: trade payments, bank data, judgments
  Cleaning, linking, history, entity IDs
  Open register data: Companies House, Gazette, Land Registry
  free
  Much of what you pay for is convenience
  Filed financials, officers and ownership are free. Vendors charge for cleaning, history, linking and a usable interface.
  The real advantage is private data
  Payment behaviour, bank data and judgment feeds are not public, and they drive the best credit scores.
  Open data can cover the bottom layers
  That is what this project does for the accounts.
  10
  --- NOTES ---
    > WHAT IT IS: the accounts bulk product contains every electronically filed set of accounts, one document per filing. Recent documents are about 99% inline XBRL (iXBRL): normal-looking HTML accounts in which each number is tagged with a machine-readable concept name, period, unit and optional dimensions (for example, creditors split into "due within one year" and "after one year").

WHY IT'S MOSTLY BALANCE SHEETS: under section 444 of the Companies Act 2006, small companies and micro-entities may file "filleted" accounts, meaning the balance sheet and notes without the profit and loss account or directors' report. Most UK companies are small or micro, so most filings have no turnover or profit. The average-employees note is generally kept, which is why headcount coverage is much higher than any income-statement item.

THRESHOLDS: from 6 April 2025, the monetary thresholds rose by about 50%, their first change since 2013. A company must meet two of the three tests for two consecutive years.

COVERAGE FROM OUR DATA (2022–23 full check): equity is present in about 92% of company-periods, cash about 43%, debtors about 32%, and property, plant and equipment about 28%. Sparsity is real and some of it is not random.

WHO USES IT: credit agencies build financial-strength indicators and ESTIMATE turnover from balance-sheet items and sector ratios because turnover is usually missing. Creditsafe publicly describes an "Estimated Turnover Indicator" built that way.

SOURCES: CH Guide accounts page; ICAEW small-company filing options; size thresholds from April 2025 (Lexology); Creditsafe report page (estimated turnover indicator).

======================================================================
SLIDE 11  (ppt/slides/slide11.xml)
======================================================================
  5 · ACCOUNTS DATA
  The accounts data: mostly balance sheets
  Every company files annual accounts; private companies have 9 months after the year-end.
  Electronically filed accounts are published in bulk, back to 2008, as tagged iXBRL.
  Tags follow Financial Reporting Council (FRC) taxonomies: FRS 105 for micro-entities, FRS 102 for others.
  Small and micro companies may file "filleted" accounts: a balance sheet and notes, with no profit and loss.
  Result: for most companies there is no turnover or profit. Headcount usually survives.
  Size bands from April 2025 (meet 2 of 3)
  Turnover
  Balance sheet
  Staff
  Micro
  ≤ £1m
  ≤ £500k
  ≤ 10
  Small
  ≤ £15m
  ≤ £7.5m
  ≤ 50
  Medium
  ≤ £54m
  ≤ £27m
  ≤ 250
  Who uses it
  Credit agencies (scores and turnover estimates), lenders, suppliers, investors, researchers and journalists.
  11
  --- NOTES ---
    > TIMELINE
- 2008: the accounts bulk product begins, but early years contain little tagged data. Our live check found iXBRL adoption in the bulk product was about 0% in 2010 and about 97% by 2014, so our dataset starts in 2014. That start date reflects machine-readable coverage, not data availability.
- April 2025: size thresholds rose by about half, so some companies moved into smaller bands with lighter disclosure.
- 2025–26: identity verification for directors and PSCs is being introduced under ECCTA. In the PSC data, verification details already appear on about half of individual PSC records.
- April 2028: accounts reforms under ECCTA, confirmed in June 2026 after a delay from 2027. Filing moves to software-only iXBRL. Small companies and micro-entities must file a profit and loss account, and the filleted and abridged options go. The government has indicated small-company P&L may not be made public.

WHAT THIS MEANS: the future data will be richer, but it will not change the past. Anyone modelling on history must work with balance-sheet-only data.

PAID EXTRAS FOR ACCOUNTS
- Estimated turnover: agencies fill the missing P&L with model estimates. These are not filed figures, so be careful using them as ground truth.
- Standardised financials: research products map different taxonomies and formats into comparable templates across years. That standardisation is the main work, and our pipeline reproduces much of it for balance-sheet items.
- HMRC holds full accounts, including P&L for small companies, with the corporation tax return. This is confidential.

SOURCES: ICAEW, "Companies House accounts changes confirmed for April 2028" (June 2026); size-threshold sources; project recon of iXBRL adoption; Creditsafe estimated turnover description.

======================================================================
SLIDE 12  (ppt/slides/slide12.xml)
======================================================================
  5 · ACCOUNTS DATA
  What's changing, and what paid products add
  2008
  Bulk accounts product starts (e-filed only)
  ~2014
  iXBRL nearly universal in the bulk data
  Apr 2025
  Size thresholds raised about 50%
  2025–26
  Identity checks for directors and PSCs
  Apr 2028
  Software-only iXBRL filing; small and micro firms must file P&L
  2028 does not fill in history: past filings stay balance-sheet-only, and small-company P&L may stay private.
  Estimated turnover
  Credit agencies estimate turnover from the balance sheet and sector ratios.
  Standardised financials
  FAME-type products map filings to comparable multi-year templates.
  Full accounts
  HMRC holds full accounts with the tax return. Not public.
  12
  --- NOTES ---
    > HONEST FRAMING: good open-source parsers already exist. The gap is an open, full-history, reconciled table, not the parsing.
    > WHAT WAS MEASURED (final results; full report in docs/accounts-parser-check.md):
    > - Fair benchmark: 5,000 filings from a 1% company sample across 2014–2026. Identical local input, one parser at a time, warm-up excluded, 3 repeats, median reported.
    > - Speed per filing: ours 0.65 ms, ixbrlparse 7.7 ms (about 12x slower), Arelle about 1 second (about 1,500x slower). For the full archive of 35.8 million filings on 8 cores: about 2 hours for ours, about 1.4 days for ixbrlparse, and about 95 days for Arelle, so Arelle is only practical as a referee on samples.
    > - Accuracy: 99.999% agreement between ours and ixbrlparse on numeric facts (dashes excluded, because we resolve a dash to 0 at the pivot step and the others do it immediately, which gives the same published value). On the 13 published WIDE columns, every disagreement traced to that dash timing or to two files ixbrlparse cannot open. The unfiltered all-facts figure (89.5%) is mostly a design difference: we keep dates as displayed text, where the others convert them.
    > - ixbrl-parse (cybermaggedon) failed on 51% of filings out of the box, so it was not pursued.
    > WHAT THE CHECK FOUND AND FIXED IN OURS:
    > - A namespace-prefix bug that silently skipped whole filings: 61,085 filings recovered, all 2014–2022. This figure is measured directly across the whole archive. An earlier sample-based estimate of ~292,000 was wrong because it was computed from stale scan files.
    > - European decimal formats (for example "4.506" meaning 4,506) read 100–1,000x wrong: 1,096 values corrected.
    > - A format spelling variant (num-dot-decimal) that blanked 540 values in three recent months: fixed.
    > - Plain-XML filings, previously skipped: about 273,000 now read using ixbrlparse. Checked against Arelle on 186 filings, with 100% agreement.
    > - No regressions: every fact in the old version is still present. The restatement rate is unchanged at 9.36%.
    > KNOWN AND DEFERRED: nested facts and text continuations affect text only (0.0015% of numeric facts, no published column). Facts with two or more breakdowns, or custom breakdowns, are skipped by design; about 38% of filings contain some.
    > WHAT PARSERS LEAVE TO YOU: repeated facts, choosing between totals and parts (Creditors is almost always given only as parts), restatements across filings (9.36%), and point-in-time selection. That is most of the work.
    > TAKEAWAY: a narrow, fast scanner cross-checked against a full parser is a better engineering choice at this scale than either alone.

======================================================================
SLIDE 13  (ppt/slides/slide13.xml)
======================================================================
  5 · ACCOUNTS DATA
  Reading a filing is solved. Building the table isn't.
  What already exists (measured on real filings)
  ixbrlparse
  99.999% agreement with ours on numbers. Reads XML, so we now use it for those. 7.7 ms vs our 0.65 ms per filing.
  ixbrl-parse
  Failed on 51% of filings out of the box.
  Arelle
  Used as referee: about 1 second per filing, so ~95 days for the archive. Confirmed the bugs we fixed.
  Datasets
  A vendor-made Kaggle set (to 2023, contents unchecked); paid DataLedger (current + prior year).
  What every parser leaves to you
  Repeats
  164 figures repeated within the 205 filings
  Totals vs parts
  99 of 107 filings give Creditors only as parts
  Restatements
  9.36% of repeated figures differ across filings
  Point in time
  Which value was known, and when
  Scale
  35.8m filings: ~2 hours for ours, ~1.4 days for ixbrlparse (8 cores)
  Filer quirks
  e.g. headcount tagged in pounds
  Could you rebuild this with ixbrlparse? Yes. Most of the work is deciding which number is true, and when it was known.
  13
  --- NOTES ---
    > DESIGN IN ONE SENTENCE: parse the difficult HTML once into a complete archive, then make cheap, repeatable tables from it.
    > STEPS
    > 1. Download: a fetch, extract and delete loop that handles one month at a time, so peak disk use stays around one ZIP plus one month of working data. It records every month as downloaded, absent or failed; all 152 months from January 2014 to August 2026 were present.
    > 2. Parse: every inline-XBRL fact is extracted, including its concept name, value, unit (pounds, count or ratio), scale (for example, thousands), sign, period and any dimension (for example, "creditors due within one year"). Text facts are kept as text; nothing is forced into a number.
    > 3. Archive (the LONG table): one Parquet file per month. In total there are about 2.0 billion facts across 4,455 distinct concepts.
    > 4. Reconcile (the WIDE table): each company-period becomes one row. Because each filing also contains the prior year as a comparative, the same figure can appear twice with different values; about 9% of repeated figures are later restated. We keep both an "as first reported" version and a "latest" version, plus cell-level provenance. At this scale, this needed an out-of-core engine (DuckDB writing directly to Parquet) on a 30 GB machine.
    > 5. Publish: WIDE and a public LONG version on Kaggle. Personal data such as director names, addresses and director loans is removed.
    > QUALITY CHECKS (worth emphasising to a data audience)
    > - Accounting invariant: every fact lands in exactly one category (kept, duplicate, conflict, skipped and so on), and the totals must match, so nothing is lost silently.
    > - Independent cross-checks: two separate implementations produced the same restatement rate. Suspiciously round numbers (exactly 0% or 100%) exposed two real bugs, which are now covered by regression tests.
    > - Representation traps: a dash in UK accounts means nil. It is now treated as 0 rather than missing, which avoids unintentional look-ahead in the as-first-reported table.
    > UPDATE (version 2 of the dataset): a three-parser check (ours, ixbrlparse, Arelle) found and fixed three bugs in our parser. It recovered 61,085 filings, corrected 1,096 values, and added about 273,000 XML filings. There were no regressions. Numeric agreement with ixbrlparse is 99.999%. Full detail is on the "Reading a filing is solved" slide and in docs/accounts-parser-check.md.

======================================================================
SLIDE 14  (ppt/slides/slide14.xml)
======================================================================
  6 · WHAT WE BUILT
  From 152 monthly archives to one analysable table
  Download
  152 monthly ZIPs, Jan 2014 – Aug 2026, one at a time
  Parse
  Every tagged fact: value, unit, scale, sign, period, dimensions. XML via ixbrlparse
  Archive
  One Parquet per month: about 2.0 billion facts, 4,593 concepts
  Reconcile
  Pivot to company × period, with restatements and provenance
  Publish
  Two Kaggle datasets, personal data removed
  How we know it is right
  Every fact read is counted into exactly one category, and the counts must add up.
  Two independent methods give the same restatement rate (7.93% vs 7.94%, 2022–23).
  Three-parser check (ours, ixbrlparse, Arelle): 99.999% agreement on numbers; bugs found and fixed.
  Creditors components checked against totals: no sign-flip errors found.
  14
  --- NOTES ---
    > WIDE (flagship)
- One row per company and period-end. The "as first reported" version has about 33.5 million rows; the "latest" version has about 36.7 million.
- Columns: the nine core balance-sheet concepts (equity, net current assets, current assets, creditors, cash, debtors, property/plant/equipment, total assets less current liabilities, average employees), plus equity split into share capital and retained earnings, and creditors split into due within and after one year.
- Helper columns: n_concepts_present, n_source_filings, row_available_yyyymm (the month by which the whole row was known), and employees_unit_anomaly.
- A matching provenance table records which filing each cell came from.

LONG (for analysts who want more than the curated columns)
- Every numeric fact from the archive, plus a short list of safe structured fields (dates, company number, dormant flag, accounting standard, filing software).
- Removed: all names, addresses, free text and director-related numbers (pay, loans, advances). With a single director, those figures relate to an identifiable person.
- The maintainer keeps a private full version.

LICENCE: source data is Companies House, published under the Open Government Licence v3.0. The OGL does not cover personal data, which is part of the reason personal data is removed before publishing.

LINKS: GitHub github.com/ThomasHSimm/open-company-uk. Kaggle links can be added once published.

======================================================================
SLIDE 15  (ppt/slides/slide15.xml)
======================================================================
  7 · USING THE DATASET
  Two datasets for two kinds of user
  WIDE: ready to model
  One row per company and period-end: about 33.5m rows (as first reported)
  Balance-sheet totals, employees, equity and creditor components
  Point-in-time and provenance columns; per-cell source table
  About 2.6 GB of Parquet
  LONG: the full archive
  Every numeric fact, not just the modelled columns
  Plus safe metadata: dates, flags, filing software
  Names, addresses and director-related figures removed
  One Parquet per year, about 9.2 GB
  152
  months
  2014–26
  continuous
  ~2.0bn
  facts
  OGL v3.0
  licence
  15
  --- NOTES ---
    > CODE: the files are Parquet, so polars, pandas, DuckDB or Spark all work. The example is illustrative; replace 00012345 with a real company number. row_available_yyyymm is the month by which every value in that row had been filed, which makes point-in-time filtering simple.

RULES OF THUMB
1. Pivot mode: "as first reported" keeps the value from the original filing. "Latest" replaces it with any later comparative restatement (about 9% of repeated figures differ). For backtesting or prediction, "latest" gives the model information that was not available at the time. Across the full span, as-first-reported keeps about 91% of latest's rows, so the leakage-safe choice costs little.
2. Creditors: in sampling, only about 4% of company-periods report a creditors total; almost all report the maturity split instead. The within/after-one-year columns are the usable signal.
3. Employees: about 29% of employee facts are tagged in pounds instead of as a count. The median value is 1, so most are real headcounts with the wrong label. The flag lets users decide; no values were removed.
4. Dashes: UK accounts use "–" for nil. Treating dashes as missing previously let a later filing's value replace a reported zero. They are now 0.
5. Missing values are not imputed. Some missingness is not random (equity coverage varies by filing month; employee coverage changes around 2020–21), so decide explicitly how to handle gaps.

======================================================================
SLIDE 16  (ppt/slides/slide16.xml)
======================================================================
  7 · USING THE DATASET
  Getting started, and rules of thumb
  import polars as pl
  wide = pl.read_parquet(
  "accounts-wide-as_first_reported.parquet")
  # one company's history
  (wide
  .filter(pl.col("company") == "00012345")
  .sort("period_end"))
  # known as of a date: no look-ahead
  wide.filter(
  pl.col("row_available_yyyymm") <= 202312)
  Company numbers are text: keep the leading zeros.
  Use "as first reported" for prediction. "Latest" includes later restatements, so it leaks the future.
  For Creditors, use the within/after-one-year columns. The total is usually blank by design.
  employees_unit_anomaly = 1 means headcount was tagged in pounds. Most are real headcounts; a few are staff costs.
  A dash in the accounts means nil, and is stored as 0.
  Blank is not zero: missing values are not imputed.
  16
  --- NOTES ---
    > Stated plainly, because each changes how the data should be used.
    > - Balance-sheet only: a feature of UK filing rules for small and micro companies, not of the pipeline.
    > - 2014 start: iXBRL adoption in the bulk product rose from about 0% in 2010 to about 97% by 2014. Earlier accounts exist but are not machine-tagged in a usable way.
    > - E-filed only: paper filings are not in the bulk product, though digital filing is now above 90% of all filings.
    > - Validation scope: coverage and internal consistency were checked for the nine core concepts. The remaining concepts are captured exactly as filed but not checked; a concept inventory lists them with anomaly flags.
    > - Restatements: 9.36% of repeated company/period/concept keys disagree across filings over 2014–2026. Early years may differ from later ones; a by-year breakdown is in the project docs.
    > - Employee break: employee coverage rose sharply between 2019 and 2021 because of a reporting change, so earlier absence is not a company signal.
    > - Non-random gaps: equity fill-rate varies by more than 10 percentage points across months.
    > - Currency: non-GBP monetary facts are kept in LONG but excluded from WIDE.
    > - Also documented: 14 period_end dates with mistyped years, and about 36,000 numeric facts with unresolved units (flagged, not fixed).
    > UPDATE (version 2): plain-XML filings are now included, read with ixbrlparse, so the old "XML skipped" limitation no longer applies. Paper filings are still not in the bulk product. The remaining completeness gap is by design: facts in contexts with two or more breakdowns (25.3% of filings contain some) or custom breakdowns (20.1%), about 38% of filings combined. These are mostly detailed notes, such as fixed-asset movements or changes in equity, not the balance-sheet totals the WIDE table uses. Text continuations and nested text facts are also not fully captured (text only, no effect on published numbers).

======================================================================
SLIDE 17  (ppt/slides/slide17.xml)
======================================================================
  7 · USING THE DATASET
  Limitations to know before modelling
  Balance-sheet only
  Most companies file no turnover or profit.
  Starts in 2014
  Earlier bulk data is barely machine-tagged.
  Some breakdowns skipped
  Facts with 2+ or custom breakdowns aren't captured; ~38% of filings have some.
  Nine core concepts validated
  The other ~4,580 concepts are captured but unchecked.
  Restatements
  About 9% of repeated figures change in later filings.
  Employee reporting break
  Coverage jumps around 2020–21 because rules changed.
  Non-random gaps
  Equity coverage varies by filing month.
  GBP only in WIDE
  Non-sterling filers are excluded, not converted.
  17
  --- NOTES ---
    > THE ACCOUNTS DATASET IS ONE PART OF open-company-uk, an open, reproducible pipeline over free Companies House data.

- Register indicators: an API-based pipeline derives transparent, rule-by-rule flags from what the registrar records (for example, overdue filings, disputed addresses, unresolved PSC statements). It is validated against Insolvency Service records. It deliberately avoids a single score, so each flag can be traced to source fields.
- Ownership and control (in progress): the PSC bulk snapshot covers about 16 million records, and history back to April 2016 can be reconstructed. The plan is company-level features such as corporate ownership chains, how many companies a person controls (with honest match confidence) and unresolved-ownership statements. Only code will be published, because PSC data contains personal data and users can download it directly from Companies House.
- Accounts: this dataset.

CLOSING MESSAGE FOR DATA PROFESSIONALS: the register is free, large and useful, but awkward to use. Much commercial value comes from making it usable. This project aims to provide an open, documented version of that usable layer, with its limitations stated plainly.

======================================================================
SLIDE 18  (ppt/slides/slide18.xml)
======================================================================
  The wider project
  Register indicators
  Transparent, rule-by-rule flags from register data, checked against Insolvency Service records. No single opaque score.
  Ownership and control
  PSC data: who controls what, links between companies, unresolved-owner statements. Code only; in progress.
  Accounts
  This dataset: 12 years of balance sheets, point-in-time safe, on Kaggle.
  github.com/ThomasHSimm/open-company-uk
  Questions and feedback welcome
  --- NOTES ---
    > Every row joins to Companies House, mostly on the company number, so each one adds a column to the same company picture rather than creating a separate project. Rows are in suggested priority order for open-company-uk.
    > 1. The Gazette: the official public record of corporate insolvency and strike-off notices, with a free official API returning JSON. Notices include the company number. For this project it provides outcome labels and, more usefully, timing: how far ahead of a winding-up petition does a register or accounts signal appear? That is a better test than "did the company fail eventually".
    > 2. HM Land Registry company ownership (UK companies and overseas companies owning property in England & Wales): free monthly CSVs keyed by company registration number, with historical files through the HMLR API. The licence restricts commercial reuse and republishing, so publish code only, as for PSC.
    > 3. Payment practices reports: large companies must report twice a year, including average days to pay, the share of invoices paid within 30, 31–60 and 61+ days, the share paid late, and payment terms. Reports carry the company number, and all published reports can be downloaded. It is the only open data on supplier payment behaviour, the thing credit agencies buy privately, but it covers large companies only.
    > 4. Contracts Finder and Find a Tender: public contracts and awarded suppliers in the Open Contracting Data Standard. Supplier identifiers are inconsistent, so matching needs work.
    > 5. Charity registers (Charity Commission, OSCR, CCNI): many charities are also companies and carry a company number.
    > 6. Register of Overseas Entities: held at Companies House, and links overseas owners of UK property to their beneficial owners. This is the bridge between Land Registry and ownership.
    > 7. FCA register: the official API is limited to about 10 requests per 10 seconds, so there is no practical bulk copy. Useful as a lookup flag.
    > Left off: HMRC VAT check (one number at a time only), the individual insolvency register (personal data), food hygiene ratings (no company numbers).
    > CONFIDENCE: access details for the Gazette, HMLR, payment practices and FCA are checked. Contracts and charity matching rates are my estimates until a recon is run.
