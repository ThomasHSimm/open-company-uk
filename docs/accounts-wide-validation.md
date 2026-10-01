# Reviewed accounts WIDE map validation

The reviewed v1 map was exercised in both provenance modes against evenly spread 1,000-member samples from the January and February 2022 archives. These partial samples validate the pivot mechanics; they are not publication coverage estimates.

| Mode | Company-period rows | Provenance cells | Unique provenance keys |
|---|---:|---:|---:|
| `as_first_reported` | 1,991 | 11,387 | 11,387 |
| `latest` | 3,719 | 21,251 | 21,251 |

Every emitted cell has exactly one `(company, period_end, wide_column)` provenance row. The `latest` output contains 9,806 cells drawn from later filings' comparative periods, demonstrating why `made_up_to_date` belongs in the side table and why `latest` is unsuitable for predictive publication.

## Null rates in this sample

| WIDE column | `as_first_reported` | `latest` |
|---|---:|---:|
| `Equity` | 7.5% | 8.0% |
| `NetCurrentAssetsLiabilities` | 20.3% | 21.1% |
| `CurrentAssets` | 28.2% | 27.6% |
| `Creditors` | 96.2% | 96.2% |
| `CashBankOnHand` | 58.9% | 58.9% |
| `Debtors` | 74.1% | 73.4% |
| `PropertyPlantEquipment` | 75.7% | 75.2% |
| `TotalAssetsLessCurrentLiabilities` | 25.4% | 25.2% |
| `AverageNumberEmployeesDuringPeriod` | 17.1% | 20.9% |
| `equity_share_capital` | 64.6% | 63.6% |
| `equity_retained_earnings` | 66.2% | 65.4% |

Missing values remain null. The 96.2% Creditors null rate is the intended genuine-total behavior, not evidence that filings lack creditor information.
