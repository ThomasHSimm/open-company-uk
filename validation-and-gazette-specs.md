# Two specs: insolvency validation harness + Gazette winding-up integration

*Design doc, August 2026. Both are for open-company-uk. Spec 1 (validation) is the
higher-value build and has no external-API risk. Spec 2 (Gazette) adds an early-warning
signal in the register-fact evidence class. Written as design first; the Claude Code
prompts at the end are derived from these.*

---

## Spec 1 — Insolvency validation harness

### Purpose
Turn "the pipeline runs" into "the indicators demonstrably separate known-insolvent
companies from the general population." This is the ORR-style external-ground-truth check:
the pipeline's insolvency/status indicators are graded against an independent labelled
set (Insolvency Service / CH record-level data), not against their own fixtures.

### What it is and is not
- IS: a positive-class recall test (do we catch known insolvencies?) plus a
  false-positive read on a control sample.
- IS NOT: a validation of "clean = trustworthy". Absence of flags stays weak evidence.
  The harness must not report anything that implies the converse.
- IS NOT: a validation of overdue-filing or PSC indicators — no external ground truth
  exists for those; they are register states read directly, true by construction.

### Ground-truth source
Insolvency Service record-level CSV (the transparency dataset / monthly-release
record-level file). **Open question to resolve before building: does it carry company
numbers or only names?** The harness is designed for both, but the name-only path needs
a manual/fuzzy match step and should be clearly quarantined as lower-confidence.

### Design

New module `src/ukcompany/validation/` (separate from the core pipeline — it is an
evaluation tool, not part of scoring):

```
validation/
├── labels.py      # load + normalise the labelled insolvency set -> {company_number: procedure_type}
├── sample.py      # draw a control sample of company numbers NOT in the labelled set
├── evaluate.py    # run derive+score over (positives + control), compute separation metrics
└── report.py      # render a text/markdown separation report
```

Flow:
1. `labels.py` reads the Insolvency Service CSV, normalises numbers via the existing
   `validate.normalise_company_number` (so Excel damage in their file is handled too),
   maps each to its procedure type (compulsory liquidation / CVL / administration / CVA /
   MVL if distinguished). Records rows with no usable number separately — reported, never
   silently dropped.
2. `sample.py` draws N control company numbers. Cleanest source: the monthly bulk
   snapshot (random rows), else a supplied list of known-active companies. Control must
   exclude anything in the labelled set. Document the sampling frame — a control drawn
   only from active companies is not the same as a random register draw, and the
   false-positive rate is conditional on that frame.
3. `evaluate.py` runs the REAL pipeline (fetch if needed → derive → score) over
   positives + control, then computes, per indicator (STATUS_INSOLVENT,
   INSOLVENCY_ADVERSE, SOLVENT_WINDING_UP) and overall:
   - recall on positives (fraction flagged), broken down BY PROCEDURE TYPE — this is the
     key table: it directly checks the MVL/solvent-vs-adverse classification against the
     official procedure label. An MVL row in the ground truth should hit SOLVENT_WINDING_UP,
     NOT INSOLVENCY_ADVERSE. A mismatch here is a real bug, not noise.
   - flag rate on the control (the false-positive read).
   - a confusion-style 2x2 (labelled-insolvent vs any-high-severity-flag).
   - explicit "missed positives" list with their current company_status, because many
     will legitimately be 404/dissolved (time gap between the label date and now — see
     temporal caveat) rather than pipeline failures.
4. `report.py` writes docs/validation-report.md (gitignored if it contains company
   numbers; template/summary version can be committed). Leads with the per-procedure-type
   recall table and the temporal-coverage caveat.

### Temporal caveat (must be stated in the report)
The live API returns CURRENT state. A company insolvent in the label year but since
dissolved-and-purged returns 404; one that restructured may show active. So recall is
expected to degrade with label age, and low recall on old labels is a data-availability
fact, not a pipeline miss. Draw positives from the MOST RECENT release to minimise this.
The harness must classify each missed positive as {404/purged, status-moved-on,
genuine-miss} so the three are never conflated.

### Success criteria
- High recall on recent adverse-procedure positives (the pipeline catches current
  insolvencies).
- Every ground-truth MVL classified as solvent, not adverse (classification correctness).
- A control false-positive rate that is understood and frame-conditional, not a single
  headline number.
- No claim, anywhere in the report, that low-flag companies are validated as sound.

### Effort
Design-complete here. Build ~2–3 evenings, most of it in labels.py normalisation and the
missed-positive classification. No external API beyond CH itself.

---

## Spec 2 — Gazette winding-up / insolvency notice integration

### Why it earns a place (unlike Contracts Finder)
A winding-up PETITION appears in The Gazette **before** company_status changes at
Companies House — it is the earliest public indicator of distress, in the same
register-fact evidence class as everything else in the pipeline (a dated, official,
recorded event). Contracts Finder was rejected because award-holding proxies sector/size,
not reliability; the Gazette is the opposite — a direct, adverse, early event.

### Access (confirmed from official DevDocs, not aggregators)
- Free feed, **no authentication required** for public notices (auth is optional and only
  adds a per-user "saved" flag — irrelevant here).
- Endpoint: `https://www.thegazette.co.uk/{service}/notice/data.json` with
  `{service}` = `insolvency` (constrains to Corporate Insolvency cat 24 + Personal
  Insolvency cat 25).
- Filter by `noticetype` (4-digit codes) and/or `categorycode`; date-range via
  `start-publish-date` / `end-publish-date` (ISO 8601); pagination via `results-page` +
  `results-page-size`; `sort-by=latest-date`. HATEOAS links give first/next/last.
- Response is Atom-derived JSON; the notice-code lives at `entry[].f:notice-code`, notice
  id/link in `entry[].id`.
- Licence: OGL (official public record). Attribution required.

### The hard part — honest flag
The feed returns notices with a **notice code, title, publication date, and a content
blob**. The **company number is inside the notice content, not a clean top-level field**
in the search-feed representation. Confirmed from live examples: notice text reads
"COMPANY NAME LIMITED (Company Number 03386960)". So the join to a company number requires
either (a) parsing the content, or (b) fetching each notice's structured representation
(the notice has .json/.xml/JSON-LD linked-data views) and reading the number from there.
**Which of (a)/(b) is reliable is the pre-build unknown** — resolve by fetching 3–5 real
insolvency notices and inspecting their linked-data JSON for a structured company-number
field before committing to a parse strategy. Do NOT build a regex-over-free-text solution
if a structured field exists in the linked-data view.

### Two usage modes — pick per task, not both at once
1. **Enrichment of a supplied list** (fits the existing pipeline): for each company
   number in the run, has a winding-up/insolvency notice been published, and when? This
   is the screening-relevant mode. But note the feed is search-by-notice, not
   lookup-by-company — you would search recent insolvency notices and JOIN to the run's
   numbers, or query per company if the linked-data supports number search. Determine
   which during the pre-build inspection.
2. **Discovery** (population monitoring): pull all insolvency notices in a date window.
   Out of scope for v1; useful later for the ORR-style "network-wide" framing.

### Design (mode 1, enrichment)

New endpoint in the existing fetch/cache pattern, but with a DIFFERENT shape — this is a
search feed, not a per-company resource, so it needs its own small module rather than
bolting onto the CH client:

```
src/ukcompany/gazette/
├── client.py    # thegazette.co.uk feed client: date-ranged insolvency search, pagination,
│                # its own polite rate limit; OGL attribution constant
├── fetch.py     # pull insolvency notices for a date window -> cache (reuse RawCache with
│                # a "gazette" pseudo-company key, or a parallel cache dir; decide in review)
├── parse.py     # notice -> {company_number, notice_code, notice_type, published, url};
│                # number extracted from the STRUCTURED linked-data view where available,
│                # free-text parse only as documented fallback with a confidence flag
└── join.py      # match parsed notices to the run's company numbers -> attributes
```

Derived attributes (registered in FIELD_DOCS, tier 1 — it is an official recorded event):
- `gazette_insolvency_notice_present` (bool)
- `gazette_earliest_notice_date`, `gazette_latest_notice_date`
- `gazette_notice_codes` (verbatim codes, e.g. winding-up petition vs resolution)
- `gazette_notice_match_confidence` ("structured" | "text-parsed") — never hide how the
  match was made.

New rule (ONE, after review of real data):
- `GAZETTE_WINDING_UP_PETITION`, severity medium, tier 1: a winding-up petition notice
  code present. Rationale for medium not high: a petition is an allegation/process start,
  can be withdrawn/dismissed, and is not yet a court order — seriousness is real but below
  a confirmed liquidation status. Exact notice codes to match determined from the
  taxonomy during build (the DevDocs notice-taxonomy lists the 24xx corporate insolvency
  codes; verify the winding-up petition code rather than guessing it).

### Caveats to document
- Personal-insolvency notices (cat 25) are individuals — OUT of scope, and a data-
  protection reason to constrain to corporate (cat 24) only.
- Notice content may name insolvency practitioners (personal data) — parse only the
  company number and notice metadata; do not derive practitioner names.
- A Gazette notice is evidence of a PROCESS, not a verified outcome — same recorded-not-
  verified framing as the rest of the project.
- Match confidence must ride with every derived flag; a text-parsed match is weaker
  evidence than a structured one.

### Effort
Larger than it looks because of the number-extraction unknown. Pre-build inspection
(fetch real notices, find the company-number field) is a MUST before any prompt is
written — this is the step that was correctly withheld from earlier handoffs. Realistic:
half an evening inspection + design confirmation, then 2–3 evenings build.

---

## Sequencing recommendation

1. **Build Spec 1 first.** Highest value, zero external-API risk, and it validates the
   insolvency indicators that Spec 2 then extends — so you want the ground-truth harness
   in place before adding another insolvency signal.
2. **Inspect the Gazette linked-data** (half evening, you not the agent) — resolve the
   company-number-extraction question. Record findings in AUDIT.
3. **Then build Spec 2** against the resolved extraction method.

## Claude Code prompts (write only after the pre-build unknowns are resolved)

Not included here deliberately. Spec 1's prompt is safe to write now EXCEPT the
labelled-file column question (numbers vs names) — resolve that first, then the prompt is
a straightforward "implement validation/ per the spec." Spec 2's prompt must wait for the
number-extraction inspection; writing it now would be the exact "confident prompt for an
unseen API shape" failure mode flagged earlier. Bring the inspection findings back and the
prompts get written in five minutes each.
