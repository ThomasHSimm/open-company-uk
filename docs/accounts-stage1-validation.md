# Stage 1 full-fact archive validation

Stage 1 was exercised over evenly spread 1,000-member samples from the January and February 2022 archives: 1,994 iXBRL filings and six plain-XML filings. The sample used `scope: all` and `kinds: all`.

## Volume and fact accounting

- LONG observations retained: 109,783
- Distinct concepts: 494
- Numeric observations: 49,099
- Non-numeric observations: 60,684
- Selected observations: 108,081
- Retained `conflict_nondimensional` observations: 1,020
- Retained `conflict_member` observations: 682
- Distinct company-period records: 3,884

The invariant closes exactly:

| Bucket | Facts |
|---|---:|
| `facts_seen` | 124,797 |
| `kept_total` | 69,362 |
| `kept_member` | 38,719 |
| `collapsed_duplicate` | 12,216 |
| `ambiguous_nondimensional` | 1,020 |
| `member_value_conflict` | 682 |
| `skipped_multimember` | 1,874 |
| `skipped_typed` | 924 |
| `bad_period_refs` | 0 |

Conflict facts are both counted in their existing accounting buckets and retained as table rows. Their storage does not add another accounting bucket.

## Size interpretation

The same sampled filings produced 26,651 rows under the nine-concept extractor and 109,783 under the full-fact default, a 4.1× row increase. This small sample is below the 5–10× full-history planning range but confirms that the old approximately 2–3 GB / 94.8× reduction estimate described only the slim nine-concept product.

Per-month Parquets are therefore the Stage 1 archive contract. No default command builds a monolithic all-history file, and no downstream process should load every month eagerly.

## Conflict policy boundary

Stage 1 records every fact from a conflicting non-dimensional or same-member group and supplies no preferred value. Grouping remains strict to `(concept, period_end, dimension, member)`: different dimensions and members are separate selected components, never competing values. Agreeing duplicates remain collapsed to one selected observation.

Existing QA and reviewed WIDE consumers use only `status = selected`. A future model-specific Stage 2 may choose another conflict policy, concept scope, or missingness treatment without re-reading the source HTML/ZIP archives.
