# The PSC file: what it is, what it can tell us, and where it misleads

*Draft for `docs/`. Numbers are from the recon run on the 2026-09-18 snapshot
(`docs/recon-psc-results.md`) unless marked otherwise. Items marked **[check]** come from outside
sources or reasoning and have not yet been confirmed against the file. All example records are
invented. No real names or dates of birth appear here.*

---

## Summary

**The file.** Companies House publishes a daily file of "people with significant control" (PSCs):
the people or companies that own or control each UK company. "Significant" roughly means one of:

- more than 25% of the shares
- more than 25% of the votes
- the right to appoint most of the board

The file has one line per *controller-of-a-company*, not one line per person. If one person controls
three companies, they appear three times. Nothing in the file says the three lines are the same
person.

**What it's good for, in this project.** Four kinds of question:

1. **Does the company say who controls it?** For example: one named owner, "we can't identify our
   owner", or "we haven't finished looking". This is reliable, because it is read straight from the
   file.
2. **How is control shaped?** For example: one person holding 75–100%, several people, or another
   company. This is reliable.
3. **Is the company owned by another company, and how deep does the chain go?** This is usable, but
   only 77.9% of corporate owners with a registration number can be linked to a live company.
4. **Do the people controlling this company also control many others?** This is the most
   interesting question and the least reliable, because it depends on guessing which lines are the
   same person.

**What it can't tell you:**

- exact ownership percentages (only bands such as 25–50%)
- owners below 25%
- full dates of birth
- home addresses
- who the legal shareholders are
- what the file looked like on any day we didn't save ourselves

**The main traps:**

- The file mixes current and ended control.
- Person matching can merge different people or split one person.
- Some dates are impossible.
- "Super-secure" means "hidden by law", not "missing".

---

## 1. What one record looks like

An invented individual record, trimmed:

```json
{
  "company_number": "00000001",
  "data": {
    "kind": "individual-person-with-significant-control",
    "name_elements": {"title": "Ms", "forename": "Alex", "middle_name": "N", "surname": "Example"},
    "date_of_birth": {"month": 3, "year": 1970},
    "address": {"premises": "1", "address_line_1": "Example Street", "postal_code": "ZZ1 1ZZ"},
    "country_of_residence": "Wales",
    "natures_of_control": ["ownership-of-shares-75-to-100-percent", "voting-rights-75-to-100-percent"],
    "notified_on": "2019-06-01",
    "ceased_on": "2023-02-10",
    "links": {"self": "/company/00000001/persons-with-significant-control/individual/<id>"}
  }
}
```

How to read it:

- **Company.** `company_number` sits *outside* `data`. The same number also appears inside
  `links.self`. A parser that only reads `data` sees no company at all. That may explain the "sparse
  company number" problem you hit before **[check which file/script that was]**. In the bulk file
  the field was present on every one of the 15.95M records.
- **Current or historical.** `ceased_on` is present, so this person *no longer* controls the
  company. 16.6% of records are like this.
- **Address.** This is the *service* address, meaning an address for correspondence. It is not the
  home address. For the 7.5M records that could be joined to the register, 78.1% have the same
  postcode as the company's registered office.
- **Identifier.** The `<id>` in `links.self` identifies this person *within this company only*. The
  same person at another company gets a different id **[check: expected from the API design, not
  yet tested on the file]**.

### Record types (kinds)

| Kind | Share | Plain meaning |
|---|---:|---|
| individual PSC | 87.1% | a named person |
| corporate-entity PSC | 6.7% | another company controls this one |
| statement | 5.8% | the company is *saying something* instead of naming someone, e.g. "no one has 25%" |
| legal-person PSC | 0.1% | e.g. a government body or corporation sole |
| beneficial-owner kinds | ~0.3% | overseas entities that own UK property, a separate regime |
| super-secure | 545 records | details withheld by law, usually for personal safety |
| exemptions | 108 records | the company is exempt, e.g. listed on a regulated market |
| totals | 1 line | a summary line at the end of the last part (see §4) |

---

## 2. What people use it for, and what this project could use

### How others have used it (evidence)

- **Global Witness (2018 and 2019).** Searched the register for suspicious or non-compliant
  entries, such as companies declaring no owner or owners linked to many companies. It found that
  most companies file simply, averaging a little over one owner each, and that thousands of entries
  looked suspicious. These are selected investigative findings, not a validated classifier.
- **Open Ownership and Tax Justice Network (2025).** Analysed a standardised 2024 copy of the
  register. They looked at:
  - companies with no individual owner
  - people linked to many companies
  - chains of corporate owners
  - odd share splits between two owners, such as 99% vs 1%

  Their three stated difficulties are the same ones listed here:
  - de-duplicating people
  - ownership given only in bands
  - separating current from historical records

  They removed inactive companies and ended relationships before analysing. Doing so cut the
  entities by about a third and the ownership links by about a tenth.
- **Follow-on paper (2026, ScienceDirect).** Used the same data to flag companies with:
  - no declared owner
  - ownership bands that can't add up
  - control through trusts

### What this project could build

Each row below is a candidate per-company feature. "Reliability" means how much we trust the feature
as a measurement, not whether it predicts insolvency. That second question is for validation.

| Question about a company | Built from | Reliability | Example value |
|---|---|---|---|
| Has it named anyone, or filed a statement instead? | kinds + statement codes | High | `psc-exists-but-not-identified` |
| How many active controllers? | records with no `ceased_on` | High, once the date rules are fixed | 1 |
| Is control concentrated? | share/vote bands | High, but coarse | one person at 75–100% |
| Do the bands add up? | bands across active PSCs | Medium | three people each at 50–75% is impossible |
| Is it owned by a company? Is that parent live? | corporate PSC + `registration_number` | Medium (77.9% link) | parent dissolved in 2021 |
| How long is the ownership chain? | repeated corporate links | Medium, and falls with depth | 3 layers |
| Is control held via a trust or firm? | `-as-trust` / `-as-firm` suffixes | High, as a descriptive fact | yes |
| Where are controllers based? | `country_of_residence`, `country_registered` | High; descriptive only (Class B) | outside the UK |
| How recently did control change? | `notified_on` / `ceased_on` history | Medium, see dates in §4 | changed 2 months ago |
| Have controllers verified their identity? | identity-verification block | High as a fact, but the rules are mid-transition | not yet verified |
| Do its controllers control many other companies? | person matching | **Low until matching is validated** | controller linked to about 40 companies |
| Is the service address the registered office? | address vs register | Medium; needs a register snapshot from the same date | yes |

For the insolvency and reliability goals, the strongest candidates are probably these. **[This is a
judgement, not yet tested.]**

- **Unresolved-control statements.** These are already a rule, `PSC_UNRESOLVED`.
- **Dissolved or unlinkable corporate parents.** For example, company A lists company B as its
  owner, but B was dissolved.
- **Recent control changes.**
- **Controllers linked to many companies.** This last one only works with honest uncertainty
  attached.

---

## 3. What is and isn't in the file

**In the file:**

- names split into parts
- month and year of birth (100% present)
- service address
- country of residence
- nationality (present, but excluded from our product)
- nature of control
- start and end of control
- corporate owner identification: registration number, country, legal form
- statement codes
- identity-verification details (on 50.6% of records)
- a sanctions flag (17 records are `True`)

**Not in the file:**

| Missing | Effect on us |
|---|---|
| Exact percentages | Can't rank "who owns most" within a band. A 26% and a 49% owner look the same. |
| Anyone below 25% | Companies with many small holders can legitimately show "no registrable person". Don't read that as evasion. |
| Day of birth | Makes person matching weaker. Many people share a name and a birth month. |
| Home address | Can only match people on service address, which is often an accountant's or formation agent's office. |
| Legal shareholders | Can't check the PSC data against the share register. That lives in confirmation statements, unstructured. |
| A person ID across companies | Every "same person" link is an inference. |
| Filing date of each change | Can't measure late reporting from this file alone. It would need filing history. **[check]** |
| Past versions of the file | Corrections and deletions are invisible unless we save daily copies. |
| Verification of what was filed | Before identity verification (ECCTA), entries were not checked by Companies House. Treat them as the company's own assertion. |

---

## 4. Problems and traps

**1. Current and historical are mixed.** The file holds 10.9M distinct companies, almost twice the
live register, because ended records and dead companies stay in.
- *Effect:* any count done without filtering answers "ever" rather than "now". The recon's "28% of
  people are linked to 2+ companies" is an "ever" figure.
- *Rule:* every feature states whether it is *active at snapshot date* or *ever*.

**2. Person matching can go wrong both ways.** The recon matched people on forename + surname +
birth year + birth month. It ignored the middle name. The sample record format suggests the field is
called `middle_name`, not `middle_names` **[check]**.

- *Wrongly merged:* two different "Alex Example"s both born 03/1970 become one person. They appear
  to control both sets of companies.
- *Wrongly split:* "Alex Example" and "Alexander Example", or a surname change, become two people.
- *Address doesn't fix this cleanly.* Service addresses are often shared offices. Matching on
  address would link unrelated clients of the same accountant.
- *Proposed handling:* never collapse people into a single ID. Keep two things side by side:
  - a **strict match**: exact normalised full name, including middle name, plus birth month and
    year
  - a **likely match**: fuzzy name plus birth month and year, with address as supporting evidence,
    carrying a score and the reasons for it

  Features then report both, e.g. "linked to 3 companies (strict), up to 11 (likely)". A user can
  see the uncertainty rather than inherit our guess.
- *How to test it:* check whether the very highly connected keys (1,067 keys on 51+ companies) are
  mostly common names. If so, that points to merging errors rather than genuine serial owners.
  Hand-check a small sample on the Companies House website.

**3. Impossible or odd dates.**
- 14,554 records end before they start.
- 23,916 start before the regime existed (6 April 2016). The earliest is the year 1083.
- End dates run up to 9999.
- 17,729 individuals were under 16 at the start date. Some of these will be real (children can
  hold shares). Some will be data-entry errors in the birth year.
- *Effect:* a naive "active on date X" test gets these wrong silently. Each needs an explicit rule
  and a count.

**4. What `notified_on` means is unclear.** It may be the date the person *became* a controller, or
the date the company *told* Companies House. Many records sit exactly on 2016-04-06, the regime
start, which suggests the first meaning, at least for early records **[check against the API
documentation]**. This matters for any "how recent was the change" feature.

**5. Super-secure is not missing.** These 545 records are legally withheld. Treating them as "no
PSC reported" would flag people protected for their safety.

**6. Statement codes are literal and contain typos.** Examples:
- `no-individual-or-entity-with-signficant-control`, with "significant" misspelt upstream.
- Scottish partnerships have their own `-partnership` variants.

Match the exact strings from Companies House's `psc_descriptions.yml`. Don't correct them.

**7. Nature-of-control strings have suffixes.** For example,
`ownership-of-shares-75-to-100-percent-as-trust` is the plain right held via a trust. There are 55
base rights once the four suffix families are removed. Group before counting, or trust and firm
holdings look like separate rights.

**8. Corporate registration numbers are messy.** Only 81.7% have the standard 8-character form.
Some failures to link will be formatting, such as missing leading zeros. Others are genuinely
foreign or dissolved companies. Normalise before concluding that an owner is "unlinkable".

**9. The 32 parts are not random samples.** Later parts are dominated by recent years, and
statements sit only in the last parts. A rate from one part is biased. Always process the full
set.

**10. The summary line is a free cross-check that we aren't using yet.** The final line of the last
part gives Companies House's own counts of PSCs, statements and exemptions. The recon counted this
line as a record but didn't store its values. The extractor should check its own totals against
it.

**11. Snapshot size.** Each part is roughly 65 MB zipped (a 2021 figure from CH Guide), so about
2 GB per day for all 32 parts **[check the current size]**. Daily archiving means roughly 0.7 TB a
year. Plan storage, or store only daily differences plus a periodic full copy.

**12. Dates of the join base.** The recon linked PSC records to a register file about 7 weeks older.
Production should pair snapshots from the same day, or say how far apart they are.

---

## 5. Data governance: a heads-up for users

This project publishes **code, not PSC data**. Anyone who runs the code downloads the file from
Companies House themselves and is responsible for how they use it. The points below are there so
users know what they are handling.

- **It is personal data.** The file holds names, month and year of birth, nationality, country of
  residence and a correspondence address for about 14 million people.
  - Public availability on Companies House does not remove data-protection duties.
  - Under UK GDPR, anyone storing or analysing it needs a lawful basis and a sensible retention
    period.
- **Nationality and age are sensitive.** This project does not use nationality as a feature,
  because it risks discriminatory outcomes (Equality Act principles). Age is kept only as 5-year
  bands in private tables and is never an indicator. Users building their own features should
  think hard before doing otherwise.
- **Aggregates can identify people.** "The controller of this company also controls 40 others"
  points at a named person when the company has a single PSC. The same applies to small counts in
  a breakdown, such as 3 PSCs resident in a given country in a given sector.
- **Some records are protected.** Super-secure records are withheld to protect people at risk. Do
  not try to fill them in from other sources.
- **Matching creates new information.** Linking records into "likely the same person" produces a
  profile that no single Companies House record contains. Treat matched outputs as more sensitive
  than the source.
- **In this project's docs**, all examples are invented or obfuscated, and published breakdowns
  suppress small counts.

## 6. Checks still to run against the file

1. Record the exact key name and fill rate for middle names in `name_elements`.
2. Confirm whether the `links.self` id ever repeats across companies. Yes would mean a usable
   person id. No would confirm there isn't one.
3. Dump the full structure of `identity_verification_details` and look for any cross-company
   identifier.
4. Read the totals line and reconcile it against our own counts.
5. Recount "linked to 2+ companies" for active-only records.
6. Measure the zipped size of today's full set of parts.
7. Settle the meaning of `notified_on` from the API documentation.

---

## Sources

- Companies House PSC snapshot download page:
  <https://download.companieshouse.gov.uk/en_pscdata.html>
- CH Guide, bulk PSC data (format, sizes, totals line; community-maintained):
  <https://chguide.co.uk/bulk-data/psc>
- Companies House `api-enumerations`, `psc_descriptions.yml` (statement codes):
  <https://github.com/companieshouse/api-enumerations>
- Jofre & Knobel (2025), *Insights from the United Kingdom's People with Significant Control
  register*, Open Ownership / Tax Justice Network, especially the Methodology and Challenges
  sections: <https://www.openownership.org/en/publications/insights-from-the-united-kingdoms-people-with-significant-control-register/>
- Global Witness, *The companies we keep*:
  <https://globalwitness.org/en/campaigns/corruption-and-money-laundering/the-companies-we-keep/>
- *Anomalies and trusts in the UK's People with Significant Control register* (2026):
  <https://www.sciencedirect.com/science/article/pii/S2949791426000205>
- Recon: `docs/recon-psc.md`, `docs/recon-psc-results.md`, `scripts/recon_psc.py`
