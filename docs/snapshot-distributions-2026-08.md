# Snapshot feature distributions (2026-08-01)

Companies: **5,695,465**. Aggregates only; no address is listed.

## Fill rate per feature

| feature | non-null | fill % |
|---|---:|---:|
| `company_number` | 5,695,465 | 100.00% |
| `company_status` | 5,695,465 | 100.00% |
| `company_type` | 5,695,465 | 100.00% |
| `date_of_creation` | 5,695,465 | 100.00% |
| `age_months` | 5,695,465 | 100.00% |
| `sic_sections` | 5,695,465 | 100.00% |
| `n_sic_codes` | 5,695,465 | 100.00% |
| `flag_dormant_sic` | 5,695,465 | 100.00% |
| `flag_non_trading_sic` | 5,695,465 | 100.00% |
| `flag_nec_sic` | 5,695,465 | 100.00% |
| `n_previous_names` | 5,695,465 | 100.00% |
| `n_charges` | 5,695,465 | 100.00% |
| `n_charges_outstanding` | 5,695,465 | 100.00% |
| `n_charges_part_satisfied` | 5,695,465 | 100.00% |
| `n_charges_satisfied` | 5,695,465 | 100.00% |
| `accounts_category` | 5,695,465 | 100.00% |
| `accounts_next_due` | 5,522,753 | 96.97% |
| `accounts_overdue` | 5,695,465 | 100.00% |
| `confirmation_statement_next_due` | 5,618,055 | 98.64% |
| `confirmation_statement_overdue` | 5,695,465 | 100.00% |
| `accounts_never_filed` | 5,695,465 | 100.00% |
| `n_companies_same_postcode` | 5,695,465 | 100.00% |
| `n_companies_same_address` | 5,695,465 | 100.00% |

## SIC and accounts/confirmation flag shares

| flag | companies | share |
|---|---:|---:|
| `flag_dormant_sic` | 112,749 | 1.98% |
| `flag_non_trading_sic` | 42,258 | 0.74% |
| `flag_nec_sic` | 955,990 | 16.79% |
| `accounts_overdue` | 420,734 | 7.39% |
| `confirmation_statement_overdue` | 723,263 | 12.70% |
| `accounts_never_filed` | 225,955 | 3.97% |

## Registered-office concentration

> The upper tail is company-formation agents and virtual-office providers, whose registered office hosts tens of thousands of companies; the single largest postcode alone exceeds 1% of all companies, which is why the postcode p99/p99.9/max coincide. No address is named here.

### By postcode (governed)

### Postcode — percentiles (over companies with a count > 0)

| p50 | p90 | p99 | p99.9 | max |
|---:|---:|---:|---:|---:|
| 17 | 1450 | 87362 | 87362 | 87,362 |

| companies sharing | count | share |
|---|---:|---:|
| 1 | 374,337 | 6.57% |
| 2-5 | 1,323,846 | 23.24% |
| 6-20 | 1,196,855 | 21.01% |
| 21-100 | 735,616 | 12.92% |
| 101-1000 | 1,333,992 | 23.42% |
| 1001+ | 639,879 | 11.23% |

### By exact normalised address (ungoverned)

### Address — percentiles (over companies with a count > 0)

| p50 | p90 | p99 | p99.9 | max |
|---:|---:|---:|---:|---:|
| 3 | 596 | 86528 | 86528 | 86,528 |

| companies sharing | count | share |
|---|---:|---:|
| 1 | 2,107,443 | 37.00% |
| 2-5 | 1,149,276 | 20.18% |
| 6-20 | 413,773 | 7.26% |
| 21-100 | 604,899 | 10.62% |
| 101-1000 | 879,054 | 15.43% |
| 1001+ | 450,051 | 7.90% |
