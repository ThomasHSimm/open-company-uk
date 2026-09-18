# Accounts concept inventory

This is the Stage 1 data dictionary generated from the configured SQLite store. It reports source facts as read and does not correct or curate stored values.

- Archives represented: 2
- Source manifests: `Accounts_Monthly_Data-January2022.zip`, `Accounts_Monthly_Data-February2022.zip`
- Concepts: 494
- Observations: 109,783

Only the nine core concepts are validated for fill-rate and reconciliation. All other concepts are captured but unvalidated; rare concepts should not be trusted without checking this inventory and the source filing.

## Read-correctness audit

- Non-numeric facts with non-null `numeric_value`: **0**
- Numeric facts with a missing or unresolved `unit`: **0**

### Non-numeric coercions by concept

None found.

### Numeric unit gaps by concept

None found.

## Anomaly flags

These flags are review cues, not corrections.

### Mixed numeric/non-numeric kind (0)

None found.

### Multiple incompatible unit families (2)

| Concept | Units |
|---|---|
| `AverageNumberEmployeesDuringPeriod` | `GBP`, `pure` |
| `ParValueShare` | `EUR`, `GBP`, `pure`, `shares` |

### Mixed instant/duration context (0)

None found.

### Name-versus-kind mismatch (1)

| Concept | Reason |
|---|---|
| `OutstandingPre-paidContributionsToDefinedContributionPlanReportingDate` | text-like name has numeric facts |

## CSV data dictionary

`accounts-concept-inventory.csv` contains one row per concept, sorted by observation count. `example_values` is a compact JSON array of up to three distinct source-text examples; examples are whitespace-normalised and truncated to 120 characters only for display.
