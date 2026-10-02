# PSC ownership-structure features (attributes only)

Report for Handoff 04 (hybrid path: one shared nature-of-control mapping, consumed by the
per-company derive path now and by the bulk-snapshot loader when `feature/psc-loader` merges).
**Attributes only — no rules, no composite score.** No names or nationality are read or emitted.

Decomposition lives in [`src/ukcompany/psc_natures.py`](../src/ukcompany/psc_natures.py); the
per-company features are emitted by `derive.derive_psc` and registered in `FIELD_DOCS`
(regenerated into [`docs/data-dictionary.md`](data-dictionary.md)).

## 1. Nature-of-control enumeration and coverage

**Source of the mapping (corrected).** An earlier draft of this report claimed the codes were
*not* in `psc_descriptions.yml`. That was wrong, and was asserted without fetching the file. The
authoritative list **is** `psc_descriptions.yml` in `companieshouse/api-enumerations`: its
`description:` section holds the **86 nature-of-control codes**, and its separate
`statement_description:` section holds the statement codes (used by
`rules.PSC_UNRESOLVED_STATEMENT_CODES`) — two sections of one file. The file was fetched
(commit `0d3fb78`), the `description:` section **vendored** as
[`tests/fixtures/psc_descriptions_natures.yml`](../tests/fixtures/psc_descriptions_natures.yml),
and `tests/test_psc_natures.py` asserts **all 86 codes decompose with zero unmapped remainder**.

Recognised **core rights** (after stripping the entity-type suffix and the band):

| Core right | Band? | Drives feature |
|---|---|---|
| `ownership-of-shares` | `25-to-50` / `50-to-75` / `75-to-100-percent`, or ROE `more-than-25-percent` | `psc_max_ownership_band` |
| `voting-rights` | same | `psc_max_voting_band` |
| `right-to-appoint-and-remove` (`-directors` / `-members` / `-person`) | no | `psc_has_appointment_rights` |
| `significant-influence-or-control` | no | `psc_has_significant_influence` |
| `right-to-share-surplus-assets` and `part-right-to-share-surplus-assets` (LLP) | yes | distinct-count only |
| `registered-owner-as-nominee` (ROE nominee, jurisdiction infix) | no | distinct-count only |

**Suffix families — more complex than "four".** The enumeration combines entity-type suffixes into
**compounds**, so `decompose_nature` strips the **longest** matching suffix (the first version
stripped only one, which half-stripped compounds into a wrong core — now fixed and tested). The
full set:

`-as-firm`, `-as-trust`, `-limited-liability-partnership`, `-registered-overseas-entity`,
`-as-firm-limited-liability-partnership`, `-as-trust-limited-liability-partnership`,
`-as-firm-registered-overseas-entity`, `-as-trust-registered-overseas-entity`,
`-as-control-over-firm-registered-overseas-entity`,
`-as-control-over-trust-registered-overseas-entity` (plus the un-suffixed `plain`). There is
**no `-se` (Societas Europaea) suffix** — matching the original note's own correction.

**Base-count reconciliation (open item before merge).** The 86 codes reduce to **7 distinct cores**
and **24 distinct suffix-stripped bases** (code with entity-suffix removed, band retained). This is
neither the handoff's "32" estimate nor the recon's "**55 distinct base rights**"
(`docs/recon-psc-results.md`) — so those three counts use **different definitions** (e.g. the recon
likely counts suffixed variants, or live-data forms beyond the enumeration). `psc_natures.py` and
the bulk loader's `psc_noc` SQL must agree on one definition before they merge; the loader also
still lists only the four single suffixes and must adopt the compound set above.

## 2. Unmapped codes and the ROE band

1. **Unknown core right** → `core=None`, collected into the per-company attribute
   `psc_unmapped_natures` and into `NatureSummary.unmapped`, never silently dropped. All 86
   published codes decompose cleanly (the §1 test), so this is **expected empty**; a value means a
   code newer than the vendored enumeration, surfaced for review.
2. **ROE "more-than" threshold** (e.g. `ownership-of-shares-more-than-25-percent-registered-overseas-entity`):
   the core is recognised and the band is **captured** as `more-than-25-percent`, but it is
   **excluded from the max-band ranking** (not ordinally comparable to the `-to-` bands), so an
   ROE-only holding yields `psc_max_ownership_band = None`. Documented in `FIELD_DOCS`; it is a
   recognised code, never listed in `psc_unmapped_natures`.

A real-cache census (codes actually seen in the register, including any beyond the enumeration)
still needs a live `ukcompany run`; the `psc_unmapped_natures` column is what collects it.

## 3. Corporate PSCs and the register join

For each **active corporate-entity** PSC, `derive_psc` captures:

- `psc_corporate_reg_numbers` — the `identification.registration_number` values, **verbatim**,
  comma-joined (company identifiers, not personal data), for a future ownership-chain join.
- `psc_n_corporate_uk_format_regno` — how many of those normalise to a valid Companies House
  company number, via `validate.normalise_company_number` (the same acceptance rule as input
  validation — one source of truth). This is a **format gate, not proof the company exists**, and
  it zero-pads short all-digit ids, so a short foreign id can read as UK-format (caveat in
  `FIELD_DOCS`).

**Ownership chains are not built** — that is the next step.

**Join rate.** On the per-company API path the live rate is
`sum(psc_n_corporate_uk_format_regno) / (corporate PSCs with any registration number)` over a real
run; it is **not measurable here** (synthetic fixtures only). Population reference from the
full-snapshot recon (`docs/recon-psc-results.md`): **91.0%** of corporate PSCs carry a
registration number, of which **77.9%** resolve to a live company — but that 77.9% was measured
against the **2026-08-01** Basic Company Data register, about **7 weeks older** than the 2026-09-18
PSC snapshot, so treat it as a lower bound and state the register date wherever it is published.

## 4. New attributes (all active-records-only)

| Field | Type | Meaning |
|---|---|---|
| `psc_max_ownership_band` | band / None | highest share-ownership band across active PSCs |
| `psc_max_voting_band` | band / None | highest voting-rights band |
| `psc_has_appointment_rights` | bool / None | any `right-to-appoint-and-remove` nature (directors/LLP members/firm-trust persons) |
| `psc_has_significant_influence` | bool / None | any `significant-influence-or-control` |
| `psc_n_distinct_natures` | int / None | distinct verbatim nature codes |
| `psc_n_individual` / `psc_n_corporate` / `psc_n_legal_person` / `psc_n_super_secure` | int / None | active PSC counts by kind |
| `psc_corporate_reg_numbers` | str / None | verbatim corporate-PSC registration numbers |
| `psc_n_corporate_uk_format_regno` | int / None | of those, count in UK company-number format |
| `psc_unmapped_natures` | str / None | nature codes with an unrecognised core right |

`None` means the PSC list was **not fetched** (unknown); a cached **404** yields the "absent"
value (`0` / `None` / `False`) — the same not-fetched-vs-legitimately-none rule the existing PSC
fields use. `psc_n_super_secure` should be read alongside the profile flag
`has_super_secure_pscs`, which can be set even when no list item appears.

## 5. ECCTA verification-as-rule — options (nothing implemented)

The ECCTA identity-verification attributes already exist (`n_psc_id_verified`,
`n_psc_id_verification_due`, `n_psc_id_statement_filed`). Whether any of them becomes a **rule** is
a **maintainer decision**; this handoff implements none. Options:

- **A — Keep as attributes (status quo, recommended for now).** Identity-verification rollout is
  mid-flight (2025–2026); absence of a verification block means *unverified-or-not-yet-due*, **not
  non-compliance**, so a rule now would fire heavily on companies that are simply not yet in scope
  — a high false-positive risk against an asymmetric signal.
- **B — `info`-severity context flag** when `n_psc_id_verification_due > 0`. Surfaces the state
  without counting toward any aggregate (`info` is excluded from totals by the existing severity
  semantics). Still exposed to the rollout-incompleteness caveat; defensible only as context.
- **C — `medium` compliance rule** once rollout is complete and a verification statement is
  genuinely overdue. Defer until ECCTA is fully in force and the due-date semantics are stable and
  confirmed live.

Recommendation: **A** now; revisit B/C when the rollout matures and the validation harness can
show the signal separates. No rule ships without that evidence.

## 6. Follow-ups

- Verify the recognised cores/suffixes against the live CH natures enumeration and a real cache
  run; fold any `psc_unmapped_natures` finding back into `psc_natures.py` (§1, §2).
- When `feature/psc-loader` merges, align its DuckDB `psc_noc` SQL to `psc_natures.py`'s constants
  (or regenerate it from them) so the two paths keep one mapping.
- Ownership-network / companies-per-person work builds on `psc_corporate_reg_numbers` (§3).
