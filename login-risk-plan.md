# Login risk analysis: IP/ASN labelling, network rebuild and risk scoring

*openbotrisk working plan · drafted 2026-10-16 · status: draft for review*

## Contents

0. How to use this plan
1. Current state
2. Workstream A: understand the data
3. Workstream B: IP/ASN labelling tool
4. Workstream C: session data acquisition and sampling
5. Workstream D: population baseline
6. Workstream E: network rebuild
7. Workstream F: risk scoring
8. Workstream G: display
9. Parked: data governance
10. Open questions
11. References

---

## 0. How to use this plan

### Task types

| Tag | Meaning |
|---|---|
| `[HUMAN]` | Done by T: accounts, questions to the supplier, judgment calls, manual review. |
| `[AGENT]` | Hand the prompt to Claude Code. Prompts contain STOP points; review each report before continuing. |
| `[INVESTIGATE]` | A question we can't answer yet. Each states the method, the expected outcome, how to be certain, and the decision it unlocks. Can be done by T or an agent. |

### Agent rules

Put this file in the working repo as `docs/plan-login-risk.md`. Every agent prompt starts with "Read section 0 of docs/plan-login-risk.md and follow the agent rules."

1. Work locally. Commit to a feature branch with clear messages. Never push, merge or open pull requests.
2. No real data in git. Exports, API pulls and downloaded label sources live under `data/`, which is gitignored. Test fixtures are synthetic only and use documentation address ranges: `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` (RFC 5737) and `2001:db8::/32` (RFC 3849).
3. Usernames, IPs and session IDs are replaced by keyed hashes (HMAC-SHA256, key from an environment variable, never committed) at ingest. One exception: IP labelling (workstream B) needs the raw IP, so labels are joined first, then the raw IP is dropped. Raw IPs are never written to disk outside the original export.
4. Every reported number carries its denominator and the filter that produced it.
5. Do not tune thresholds, weights or category factors unless the prompt says so. Report, then STOP.
6. Use DuckDB on Parquet for anything that doesn't fit comfortably in memory.
7. If the data contradicts an assumption in the prompt, stop and report rather than working around it.

### Sequencing

Phase 1 needs only the login export and public label sources, so it can start now:

- A1–A6 → B1–B6 → E1–E3 using external labels only → F1–F2 without session-derived features.

Phase 2 needs the session API:

- A7 → C1 (gate) → C2–C4 → B7–B9 → D1–D3 → E4 → F1–F2 extended → F3–F5.

Phase 3:

- G1–G2.

Phase 1 alone should show whether network-type labelling fixes the giant-component problem. If it does, phase 2 becomes enrichment rather than a rescue.

---

## 1. Current state

### Data inventory

| Dataset | Fields (as currently known) | Scope | Known issues |
|---|---|---|---|
| Login export | time, IP, username, ASN, country, supplier-calculated ID (intended to identify a person rather than an account), speed/distance indicator from IP geolocation | High-activity users only; selection rule unknown | Selection bias. Unknown whether failed or blocked attempts are included. ID derivation unknown. |
| Session API | IP, session ID, time, session details, device settings (PC/phone etc.) | Assumed to be all traffic | Very large. No confirmed shared key with the login export other than IP and time. |

### Findings so far

- Linking users through shared supplier IDs: largest group 7 users, next 3. Almost no cross-account sharing.
- Linking users through shared IPs (at least 3 shared): one giant component, then a few small groups.

### Working hypotheses

None of these is confirmed, and several could be true at once.

| ID | Hypothesis | Tested by |
|---|---|---|
| H1 | The giant component is held together by a small number of hub IPs (mobile carrier NAT, corporate or university networks, VPN exits), not by coordination. | A5, E3 |
| H2 | The supplier ID is tied to one account by construction, so it can't link accounts. | A1, A2 |
| H3 | The high-user filter removes most credential-stuffing victims, who typically receive only one or two attempts each. That alone would explain small cross-account groups. | A1, A3 |
| H4 | The export is post-filter: traffic the supplier blocked is absent. | A1, A4 |
| H5 | Network type (mobile, education, hosting, residential…) changes what IP sharing and IP diversity mean. Using it will improve both linking and scoring. | B, E3, F3 |

---

## 2. Workstream A: understand the data

### Background

Several design decisions depend on facts we don't have yet: whether the supplier ID can link accounts at all, how users were selected, and whether blocked traffic is in the export. Each one changes which threats this dataset can show.

Doing these first avoids building on a misunderstanding. For example, "few small clusters" could be read as evidence of no coordination, when the selection rule may simply have removed the coordinated victims.

### A1 `[HUMAN]` Questions for the supplier

Send one message covering:

1. How is the login/user ID calculated, and from which inputs (device, cookies, account)? Can one ID appear on several usernames? Can one person get several IDs?
2. How were the high users in the export selected? Login count over what period, or something else?
3. Does the export include failed, challenged or blocked login attempts? Is there an outcome field we don't have?
4. Which geolocation/ASN database produced the ASN and country fields, and is the lookup done at event time?
5. How is the speed/distance indicator computed (geolocation level, threshold)?
6. Session API: rate limits, available filters (by IP list? by time range?), retention period, cost, and any field shared with the login export (session ID, the same user ID).
7. Do session records carry any bot score or classification from your side?
8. Terms of use: what may we store, for how long, and for what purposes?

**Expected outcome:** written answers saved to `docs/supplier-answers.md` with the date.

**How to be certain:** answers are in writing. Where an answer is vague, A2–A4 check it against the data.

### A2 `[INVESTIGATE]` What the supplier ID actually links

**Question:** can the ID link different accounts, or is it effectively per account?

**Method:** distribution of usernames per ID and IDs per username. For IDs seen on more than one username, check whether those usernames are active at the same time (shared device) or one after another (account handover or reused device).

**Expected outcome:** if well under 1% of IDs ever appear on more than one username, the ID is effectively per account. In that case, use it only for device novelty within an account (a takeover signal), not for linking accounts.

**How to be certain:** the empirical result agrees with the supplier's answer to A1 Q1. If they disagree, trust neither until resolved.

**Decision unlocked:** whether the supplier ID enters the cross-account graph (E) or only the per-user features (F).

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task A2: characterise the supplier ID in the login export at <LOGIN_PATH>.

Stage 1 — schema. Print column names, types, row count, date range and null
rate per column. Identify which column is the supplier ID and which is the
username. If either is ambiguous, STOP and report.

Stage 2 — distributions. Compute:
  - usernames per supplier ID: number of IDs with 1, 2, 3–5, 6–10, >10 usernames
  - supplier IDs per username: same buckets
  - ID lifetime (first seen to last seen): quantiles 50/90/99/max
For every ID with more than one username, classify the pair(s) as
"overlapping" (both usernames active within the same 24 h window) or
"sequential", and report counts.

Output docs/findings/a2-supplier-id.md with tables, denominators and the
queries used. Change no other code. STOP and report.
```

### A3 `[INVESTIGATE]` How the high-user set was selected

**Method:** histograms of logins per username and distinct IPs per username across the export. A cut based on login count shows up as a hard floor in the first histogram.

**Expected outcome:** a sharp floor at some login count. If the floor is instead on IP or country diversity, the export was selected on the very features we want to score. That would be a serious problem and must be stated in every result.

**How to be certain:** a floor visible in the histogram and consistent with the supplier's answer to A1 Q2.

**Decision unlocked:** which threats this dataset can and can't show, and the standard limitation statement attached to every output.

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task A3: find the selection rule of the login export at <LOGIN_PATH>.

For each username compute: logins, active days, distinct IPs, distinct ASNs,
distinct countries, first and last login. Plot histograms (log x-axis where
useful) of logins and distinct IPs per username, and report the minimum and
the 1st/5th percentiles of each. Report whether any of these has a hard
floor (many users at exactly the minimum, none below).

Output docs/findings/a3-selection.md with plots. STOP and report.
```

### A4 `[INVESTIGATE]` Outcome and filtering

**Method:** look for outcome or status fields and their distinct values. After B4, check how many logins come from hosting ASNs at all.

**Expected outcome:** if there's no outcome field and almost no hosting traffic, that's consistent with a post-filter export. This is weak evidence on its own: a target that attracts few attacks would look the same.

**How to be certain:** only the supplier can confirm (A1 Q3).

### A5 `[AGENT]` Diagnose the giant component

**Background:** for the rule "share at least one IP", connected components of the user–user projection are the same as components of the bipartite user–IP graph. Compute them on the bipartite graph and avoid the projection, whose cost is quadratic in IP degree. The "at least 3 shared IPs" rule does need pair counts, so cap IP degree first.

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task A5: test whether hub IPs cause the giant component (hypothesis H1).
Input: login export at <LOGIN_PATH>.

Stage 1 — IP degree. For each IP: distinct usernames, logins, active days,
ASN, ASN name, country. Report quantiles (50/90/99/99.9/max) of distinct
usernames per IP, and the top 30 IPs by distinct usernames with those
fields (IPs hashed in the report).

Stage 2 — components. Build the bipartite username–IP graph (igraph or
networkx). Compute connected components; these equal the components of the
"share at least 1 IP" projection. Report the sizes of the 5 largest
components as counts and as a share of all usernames.

Stage 3 — removal curve. Remove IPs in descending order of distinct
usernames: top 0, 10, 25, 50, 100, 250, 500, then top 1%, 2%, 5% of IPs.
After each step, recompute the largest component's share of usernames.
Save as CSV and as a line plot (x: IPs removed, log scale; y: largest
component share). List the ASNs of the IPs removed up to the steepest drop.

Stage 4 — at least 3 shared IPs. Excluding IPs with more than <CAP, default
200> distinct usernames, count shared IPs per username pair via a self-join
on IP, keep pairs with 3 or more, and report component sizes.

Output docs/findings/a5-hubs.md plus CSV and PNG in docs/findings/.
STOP and report. Do not change any weighting or clustering code.
```

**Expected outcome:** the largest component's share drops steeply after removing a small number of IPs (tens to low hundreds), and those IPs sit on mobile, education/corporate or VPN/hosting ASNs.

**How to be certain:** the steep drop in the removal curve plus the ASN names of the removed IPs. If there's no steep drop, the giant component comes from many moderately shared IPs, and time co-occurrence (E1) matters more than removing hubs.

### A6 `[AGENT]` IP→ASN consistency and IPv6 share

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task A6, input <LOGIN_PATH>:
1. Count IPs seen with more than one ASN, and with more than one country,
   over the export period. Give up to 10 examples of each with dates.
2. Count logins and distinct IPs by IP version (4 vs 6).
3. For IPv6: count distinct full addresses vs distinct /64 prefixes, overall
   and per username (median, 90th percentile).
Output docs/findings/a6-consistency.md. STOP and report.
```

**Expected outcome:** well over 99% of IPs have a single ASN (high confidence). Multiple countries per IP will be more common, from geolocation database updates and VPNs. If IPv6 is a material share, users will show many more distinct full addresses than /64 prefixes.

**How to be certain:** the counts.

**Decision unlocked:** whether ASN can be treated as a fixed attribute of an IP within the export window (expected yes). If IPv6 is material, every IP-level feature uses the /64 for IPv6, because devices rotate privacy addresses within a /64 (RFC 8981); counting full addresses would inflate diversity.

### A7 `[INVESTIGATE]` Session API capability

**Method:** T reads the API documentation `[HUMAN]`. An agent then does a probe pull of one peak hour and one off-peak hour `[AGENT]`: field list, types, null rates, records per hour, distinct IPs per hour, and any field that also appears in the login export.

**Expected outcome:** volume per hour (which sets the sampling budget for C) and the list of device fields (which sets what B7 and F can use).

**How to be certain:** probe numbers for both hours, scaled to a day, plus the documented rate limits.

**Decision unlocked:** whether a targeted pull by IP is feasible (C2), and the sampling fraction for the baseline (C3).

This probe is the only session pull allowed before gate C1.

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task A7: probe the session API.
Using the credentials in <ENV_VAR_NAME> and the docs at <API_DOCS_PATH>,
pull all sessions for one peak hour <PEAK_HOUR> and one off-peak hour
<OFFPEAK_HOUR>. Respect the documented rate limits. Hash IPs and session
IDs at ingest (do not label in this task). Store under data/probe/.

Report: field list with types and null rates; example values for device
fields (no identifiers); records and distinct hashed IPs per hour; any
field whose name or content suggests a link to the login export; time
taken and API calls used. Do not pull anything beyond those two hours.

Output docs/findings/a7-session-probe.md. STOP and report.
```

---

## 3. Workstream B: IP/ASN labelling tool

### Background

IP links are currently scaled by frequency only: the number of users seen on the IP. That's a reasonable start, but it treats every network the same, when the meaning of sharing depends on the type of network:

- Many users on one mobile carrier IP or university IP is normal and says almost nothing about them.
- Two accounts on one rare home-broadband IP is strong evidence of the same household or the same proxy exit.
- Two accounts on one small hosting IP is suspicious, because real users rarely log in from datacentres. Many users on a large commercial VPN exit is not.

The same applies to scoring. Ten IPs rotating within one mobile carrier is ordinary. Ten IPs across unrelated networks is not. IPs on hosting or listed networks are worse still.

#### Taxonomy

Two independent axes: network type and geography.

| Network type | Meaning | Domestic? |
|---|---|---|
| `residential_fixed` | Consumer home broadband | Yes |
| `mobile` | Mobile carrier, usually behind carrier-grade NAT | Yes |
| `business` | Enterprise or business ISP | No |
| `education` | Universities and research networks (e.g. Jisc/Janet) | No |
| `government` | Public-sector networks | No |
| `hosting_cloud` | Datacentre, cloud, hosting | No |
| `vpn_proxy_listed` | On a VPN or proxy list | No |
| `tor_exit` | Tor exit node | No |
| `hostile_listed` | On a hostile-network list (e.g. Spamhaus ASN-DROP) | No |
| `unknown` | No label | n/a |

Geography: country code, plus a UK / non-UK flag for convenience.

Caveat: many ISPs serve homes and businesses from the same ASN, so residential vs business is coarse at ASN level. Prefix-level and behavioural labels improve on that.

#### Residential does not prove a real user

Residential proxy services route traffic through real consumer connections, so a bot operation can appear domestic. It costs more than datacentre infrastructure, because residential proxies are usually sold by bandwidth. (Moderate-to-high confidence on the direction. Use the metering-model table on the economics-of-automation page for grounded figures; don't quote prices here.)

That cost shapes behaviour, and behaviour is what we can detect:

- Each residential IP is used briefly and sparingly.
- One actor hops across many unrelated consumer ISPs, often in different regions or countries. A real user typically has one or two home connections plus one mobile carrier, stable over months.
- The device and network layers often don't agree: device timezone or language doesn't match the IP's country.

So `residential_fixed` should lower the prior risk of a single IP, but residential hopping is itself a risk feature (F1). External lists will never catch residential proxies. Only behavioural labels (B7) and per-user features (F1) can.

#### Sources

| Source | Gives | Licence / terms | Caveats |
|---|---|---|---|
| IPinfo Lite | Country and ASN per IP, IPv4 and IPv6, updated daily; CSV, MMDB, JSON or Parquet | Free, product use allowed with attribution | No network type |
| ASdb (Stanford) | ASN → organisation and up to three industry categories; 17 categories, 95 sub-categories | Research dataset; check terms (B2) | Categorisation rerun roughly annually; latest snapshot March 2026. Published accuracy 93% (category) and 75% (sub-category). Probably doesn't separate mobile from fixed broadband (to check in B5). |
| Spamhaus ASN-DROP | ASNs controlled by spammers or criminals, plus hijacked ASNs | Free under Spamhaus terms; contents protected by copyright and database right | Fetch at most hourly. Fine as an internal feature; don't republish. |
| Tor exit list | Current Tor exit IPs | Public (Tor Project) | Changes constantly; store with retrieval date |
| Cloud provider ranges | Published IP ranges for AWS, Google Cloud, Azure, Oracle, Cloudflare, etc. | Public | Covers big clouds only; small hosting providers come via ASdb |
| Community VPN lists (e.g. X4BNet lists_vpn) | VPN and datacentre ranges | Check each repo's licence | Quality varies; often stale |
| Manual anchors (B6) | Hand-checked network type for the top ASNs | Ours | Small but high-confidence; also used as ground truth in B8 |

CAIDA's AS classification dataset is no longer available, so it's not an option.

#### External vs behavioural labels

Keep both, as separate rows. Disagreement is a signal in itself: an IP listed as a consumer ISP that behaves like a proxy (many unrelated users, uniform devices, bursty activity, layer mismatches) is a residential-proxy candidate (B9).

#### Table design

Long format: one row per (range, source, label axis).

| Column | Notes |
|---|---|
| `ip_version` | 4 or 6 |
| `range_start`, `range_end` | IPv4: uint32. IPv6: upper 64 bits as uint64 (see below) |
| `prefix` | CIDR text, for readability |
| `asn` | Where known |
| `level` | `ip`, `prefix` or `asn` |
| `axis` | `network_type`, `country` or `listed` |
| `value` | Taxonomy value |
| `source` | e.g. `ipinfo_lite`, `asdb`, `spamhaus_asn_drop`, `manual_anchor`, `behavioural_v1` |
| `source_version` | File date or snapshot ID |
| `retrieved_at` | Date |
| `licence` | Short ID plus link to the saved licence text |
| `confidence` | Source-stated where available, otherwise assigned and documented |
| `notes` | Free text |

**Resolution:** within a source, the most specific level wins (IP over prefix over ASN). Across sources, keep all rows. A derived `resolved_network_type` can follow a documented precedence, but raw rows are never discarded.

**IPv6:** treat the /64 as the unit equivalent to one IPv4 address, since devices rotate privacy addresses within a /64 (RFC 8981). Routed prefixes are almost always /48 or shorter, so the upper 64 bits are enough to store and join IPv6 ranges as plain 64-bit integers. Single-address lists such as Tor exits collapse to their /64. (High confidence on /64 rotation; moderate on "almost always /48 or shorter", so verify on the data.)

**Lookup:** a range join in DuckDB (`ip_int BETWEEN range_start AND range_end`), one pass per IP version.

### B1 `[HUMAN]` Accounts and downloads

- IPinfo: create an account, get a token, download IPinfo Lite as Parquet. Note the attribution requirement.
- ASdb: download the latest categorised-ASes CSV from asdb.stanford.edu.
- Spamhaus: download ASN-DROP (JSON) and save the terms page.
- Tor Project: download the bulk exit list.
- Cloud ranges: AWS, Google Cloud, Azure, Oracle, Cloudflare, plus any other provider that shows up among the top ASNs after B4.
- Decide whether to use a community VPN list, and record why.

For each source, save the licence or terms text under `data/external/licences/` and add a row to `data/external/SOURCES.md`: source, URL, date retrieved, licence, whether redistribution is allowed.

**Expected outcome:** all files under the gitignored `data/external/`, and `SOURCES.md` complete.

**How to be certain:** every source in `SOURCES.md` has saved licence text.

### B2 `[INVESTIGATE]` What can be published

**Question:** which derived labels or results can appear on openbotrisk?

**Expected outcome:** IPinfo Lite can be used with attribution. Spamhaus is fine as an internal feature, but derived lists shouldn't be republished. ASdb terms are unknown and need checking. Cloud ranges and Tor exits are public.

**How to be certain:** quote the relevant clause for each source in `SOURCES.md`.

**Decision unlocked:** what the public page can show. Likely aggregates by network type, never lists of IPs or ASNs.

### B3 `[AGENT]` Ingestion and unified label table

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task B3: build an IP/ASN label table from external sources.

Location: <REPO>/iplabels/ (new package). Sources are already in
data/external/ (see data/external/SOURCES.md). Do not download anything.

Stage 1 — parsers. One module per source: ipinfo_lite, asdb,
spamhaus_asn_drop, tor_exits, cloud_ranges, and manual_anchor (from
data/external/manual_anchors.csv if present). Each parser returns rows in
the schema in section 3 of the plan ("Table design"). Write unit tests per
parser using small synthetic fixtures with documentation ranges only
(RFC 5737 / RFC 3849). STOP and report: row counts per source, parse
failures, and any field you had to guess.

Stage 2 — unify. Combine into one long table and write it as Parquet to
data/labels/labels_<YYYY-MM-DD>.parquet. IPv4 ranges as uint32
start/end; IPv6 as the upper 64 bits (uint64) start/end, with
single addresses normalised to their /64. Tests: first and last address
of a range, overlapping ranges from different sources, nested prefixes
within one source.

Stage 3 — summary. Write docs/findings/b3-labels.md: rows per source and
axis, IPv4/IPv6 split, ASNs per network_type per source, and every ASdb
category value encountered, with counts (needed for B5). STOP and report.

Do not build precedence or resolution logic yet.
```

**Expected outcome:** one Parquet label table, passing tests, and a summary.

**How to be certain:** boundary tests pass, and a few known anchors return the expected labels: an IP from a cloud provider's published ranges, an IP in a Jisc/Janet prefix, and a Spamhaus-listed ASN.

### B4 `[AGENT]` Lookup and coverage on the login export

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task B4: label every IP in the login export.

1. Implement lookup() in iplabels/lookup.py: a DuckDB range join per IP
   version, returning all matching rows (all sources, all levels). Add a
   helper that returns the most specific row per source.
2. Join labels onto the distinct IPs of <LOGIN_PATH> BEFORE hashing. Write
   the labelled distinct-IP table, with hashed IPs only, to
   data/labels/login_ip_labels.parquet. Raw IPs must not be written anywhere
   else.
3. Coverage report: share of distinct IPs and of logins with at least one
   label, per source and per axis; network_type distribution per source;
   share unknown. Check that IPinfo's ASN matches the export's ASN field and
   report the mismatch rate.
4. ASN concentration: cumulative share of logins covered by the top
   10/25/50/100/250 ASNs, with ASN names (needed for B6).

Output docs/findings/b4-coverage.md. STOP and report.
```

**Expected outcome:** near-complete ASN and country coverage; partial network-type coverage; mobile probably not separable from fixed broadband using external sources.

**How to be certain:** the coverage numbers.

### B5 `[INVESTIGATE]` Map ASdb categories to the taxonomy

**Method:** take the ASdb category values from B3 for ASNs present in the login export, ordered by login volume. Map each to the taxonomy by hand and list the ones that don't map.

**Expected outcome:** hosting and education map cleanly. ASdb probably doesn't separate mobile from fixed broadband (low-to-moderate confidence; check the category list). If so, mobile comes from B6 and B7.

**How to be certain:** the share of login volume with a confident mapping.

### B6 `[HUMAN]` Hand-label the top ASNs

**Why:** login volume is usually concentrated in a small number of ASNs, so hand-labelling the top ones covers most traffic cheaply. Verify the concentration with B4 step 4 first.

**Method:** for the top ASNs covering around 90% of logins (perhaps 50 or so), confirm network type using bgp.tools, RIPEstat, PeeringDB and the operator's own website. Mark UK mobile carriers, Jisc/Janet (AS786), major consumer ISPs, and business or hosting providers. Save as `data/external/manual_anchors.csv` with columns `asn, network_type, evidence_url, checked_at, use_for`, where `use_for` is `fit` or `holdout` (roughly a third held out, spread across network types). Where an ASN mixes types (e.g. one operator's fixed and mobile networks), note it rather than forcing a single label.

**Expected outcome:** a short, high-confidence list that covers most logins.

**How to be certain:** the coverage curve from B4, and an evidence URL on every row.

These anchors also serve as ground truth for validating behavioural labels (B8). The holdout rows keep B8 from being circular: thresholds are set on `fit` rows and tested on `holdout` rows.

### B7 `[AGENT]` Behavioural profiles

Needs session data from workstream C.

Features per IP, per prefix (/24 for IPv4, /64 for IPv6) and per ASN, computed within each sampled window:

| Feature | Definition | What it separates |
|---|---|---|
| `users` | Distinct users, or sessions where there's no user | Shared vs individual |
| `sessions_per_user` | Sessions / users | Heavy individuals vs crowds |
| `phone_share` | Share of sessions from the phone device class | Mobile carrier NAT |
| `device_diversity` | Entropy over device signatures | Shared facility (high) vs proxy farm (low) |
| `office_hours_share` | Share of activity 09:00–17:00 on weekdays, local time | Universities and offices |
| `night_share` | Share of activity 00:00–06:00 local time | Automation, other time zones |
| `ip_churn` | Distinct IPs per day and median IP lifetime (prefix/ASN level) | Carrier NAT pools, proxy rotation |
| `mismatch_rate` | Device timezone vs IP country; browser language vs IP country | Proxies, VPNs |
| `burstiness` | Coefficient of variation of inter-arrival times | Scripted activity |
| `user_stability` | Share of users seen on two or more days | Stable populations vs one-off traffic |

Labels such as `cgnat_like`, `shared_facility_like`, `proxy_like` and `individual_like` come later, from transparent rules whose thresholds are set from the anchor distributions in B8, not guessed in advance.

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task B7 (stage 1 only): compute behavioural profiles.

Input: baseline session data in data/sessions/baseline/ (from C3) and
the label table from B3/B4. Compute the features listed in section 3 of
the plan ("B7") per hashed IP, per prefix (/24 IPv4, /64 IPv6) and per
ASN, separately for each sampling window. Write Parquet to
data/labels/behavioural_<window>.parquet.

Then, for each anchor group in data/external/manual_anchors.csv (only rows
marked use_for=fit), plus cloud ranges and Jisc/Janet, report the
distribution (median, 10th and 90th percentiles) of each feature.

Output docs/findings/b7-profiles.md. Do NOT assign labels or thresholds.
STOP and report.
```

### B8 `[INVESTIGATE]` Validate behavioural labels against anchors

**Question:** do the behavioural features separate the known network types?

**Method:** compare feature distributions across anchor groups (Jisc/Janet, cloud ranges, UK mobile carriers, consumer broadband). T sets rule thresholds from the fit anchors; an agent then applies the rules and reports a confusion matrix on the held-out anchors.

**Expected outcome:** mobile shows high `phone_share` and high `ip_churn`; education shows high `office_hours_share` and high `device_diversity`; cloud shows low `phone_share` and high `mismatch_rate` and `burstiness`.

**How to be certain:** the confusion matrix on held-out anchors, with counts. If the anchor groups don't separate, the features are too weak to label unknown networks and shouldn't be used for that.

### B9 `[AGENT]` Label disagreement report

Prefixes labelled `residential_fixed` by external sources but `proxy_like` behaviourally become an internal candidate list. Report the count, examples (hashed), and how many users touch them. Internal only (see B2).

---

## 4. Workstream C: session data acquisition and sampling

### Background

The session data serves two purposes with different requirements:

- **Enrichment:** joining sessions to specific logins to add device details and consistency checks. This needs a targeted pull and a good join.
- **Baseline:** population rates for network type, devices, timing and mismatches. This needs no join, just a representative sample.

**Sampling.** Uniform random sampling of rows damages what we need: it thins out co-occurrences, undercounts users per IP and fragments the graph. Use instead:

- full data within selected time windows;
- entity sampling: keep all records for IPs whose keyed hash falls in a chosen bucket;
- targeted pulls for the IPs that appear in the login export.

**Joining on IP and time** is probabilistic. Behind carrier NAT or a corporate proxy, one login can match dozens of sessions. Unambiguous matches will come mostly from home broadband and uncommon IPs, and mobile users will mostly fail to match. That adds a second selection layer on top of the high-user filter, and it must be documented.

### C1 `[HUMAN]` Gate: permission to pull and store

Governance is parked (section 9), but before any bulk pull, confirm in writing that the supplier's terms allow pulling and storing session data for this purpose, and for how long.

**Expected outcome:** written confirmation in `docs/supplier-answers.md`.

**How to be certain:** it's written down. Until then, only the A7 probe is allowed.

### C2 `[AGENT]` Targeted pull for enrichment

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task C2: targeted session pull for the login export.

For each login in <LOGIN_PATH>, request sessions on the same IP within
± <WINDOW, default 5 min> of the login time. Batch requests by IP and day.
Make the pull resumable (record completed batches), respect the rate limits
in docs/findings/a7-session-probe.md, and back off on errors.

At ingest: join IP labels (iplabels.lookup), then hash IP and session ID.
Store Parquet under data/sessions/targeted/, partitioned by date.

Run ONE day of logins only. Report: sessions pulled, API calls, time taken,
storage used, errors, and the projected totals for the full export.
STOP and report before pulling more.
```

### C3 `[AGENT]` Baseline pull with entity sampling

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task C3: baseline session sample.

Windows: <WINDOW_1> and <WINDOW_2>, each 7 consecutive days, at least a
month apart. Within each window keep ALL sessions whose
HMAC(key, IP or IPv6 /64) mod <N> == 0. Use the same key for every pull so
the same IPs are always in or out of the sample.

Choose <N> using the volumes in docs/findings/a7-session-probe.md so that
total storage stays under <STORAGE_BUDGET>; propose N and STOP for approval
before pulling.

At ingest: join IP labels, then hash IP and session ID. Store under
data/sessions/baseline/<window>/. Report the realised sampling fraction
(sampled distinct IPs / all distinct IPs, from a one-hour full pull).
STOP and report.
```

**Why this design:** entity sampling keeps every record for a sampled IP, so users-per-IP and per-prefix behaviour stay complete. Two separated weeks cover weekdays, weekends and all hours, and show whether patterns are stable. Anything outside the windows is invisible; state that.

### C4 `[INVESTIGATE]` Join quality

**Question:** how reliably can a login be matched to its session?

**Method:** for each login, count candidate sessions on the same IP within windows of 10 s, 1 min and 5 min. Report the distribution of candidate counts and the unique-match rate by network type and window.

**Expected outcome:** unique matches are mostly `residential_fixed`; `mobile` is mostly ambiguous.

**How to be certain:** if any subset of logins shares a real key with sessions (A1 Q6), use it as ground truth and measure the precision of IP+time matching. Otherwise use a plausibility check (does the matched session's device class agree with the user's device history?) and report results as unverified.

**Decision unlocked:** use enrichment only for unique matches within the tightest window that keeps a usable match rate, and document which users that excludes.

---

## 5. Workstream D: population baseline

### Background

The high-user export can't show what's normal; the baseline can. Two caveats apply throughout:

- **Sessions are not users.** Heavy users and bots generate many sessions, so session-weighted rates over-represent them. Report session-weighted and IP-weighted rates side by side.
- **The baseline contains bots.** It describes all traffic, not normal users. Use medians and percentiles, and say so.

### D1 `[AGENT]` Base rates

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task D1: population base rates from data/sessions/baseline/.

Per window, compute session-weighted and IP-weighted:
  - network_type mix (resolved and per source), country mix, UK/non-UK
  - device class mix
  - hour-of-day and weekday profiles
  - users (or sessions) per IP: quantiles, per network_type
  - mismatch rates (timezone vs IP country, language vs IP country) per
    network_type
Compare the two windows and flag any rate that differs by more than
<THRESHOLD, default 20% relative>.

Output docs/findings/d1-baseline.md with tables and plots. STOP and report.
```

### D2 `[AGENT]` Quantify the high-user bias

Compare the login export with the baseline on every feature computable in both: network-type mix, country mix, hour profile, users per IP. Output a table of ratios with confidence intervals (bootstrap over IPs).

**Expected outcome:** the export over-represents residential and under-represents hosting (if H4 holds) and has a narrower hour profile.

**How to be certain:** ratios with intervals; differences that are stable across both windows.

### D3 `[INVESTIGATE]` How much of the baseline is automated?

**Method:** bound it using the share from hosting and listed networks, the `proxy_like` share from B8, and any supplier bot flag (A1 Q7).

**Expected outcome:** only a range, not a number.

**How to be certain:** state the method and the range. Don't present a point estimate.

---

## 6. Workstream E: network rebuild

### Background

**Edge weight.** For users *u* and *v*:

w(u, v) = Σ over IPs *i* shared by u and v of r(i) × c(type(i)) × τ(u, v, i)

- **r(i), rarity:** 1 / log(1 + dᵢ) (Adamic–Adar) or 1 / dᵢ (resource allocation, penalises hubs harder), where dᵢ is the number of distinct users on IP *i*. Better: rarity *within* network type, i.e. compare dᵢ with the distribution of d for that type, so an ordinary mobile IP isn't treated like a rare one.
- **c(type), category factor:** from a config file. These are judgment calls, so they're published and tested (E4). Placeholder starting values, not recommendations: mobile 0.1, education and business 0.2, residential_fixed 1.0, hosting_cloud 1.0–1.5, large commercial VPN 0.3, hostile_listed 1.5.
- **τ, time co-occurrence:** exp(−Δt / τ₀), where Δt is the gap between the two users' closest logins on IP *i*. Start with τ₀ of 5–10 minutes, or use a binary window.
- **Hub cap:** drop IPs above a user-count cap before projecting. An IP with d users creates d(d−1)/2 pairs, so a 5,000-user IP alone gives about 12.5 million.
- **Optional prefix term:** for hosting only, a reduced-weight term for sharing a /24, since automated traffic often spreads across adjacent datacentre IPs.
- **Supplier ID:** include only if A2 shows it can link accounts.

**Clustering.** Leiden, with a resolution sweep (or the CPM objective) because modularity can absorb small tight groups into larger ones (Fortunato & Barthélemy 2007), and a small bot ring is exactly that kind of group. Check stability across random seeds.

**Null models.** Leiden always returns a partition, even on random data, so every result is compared against a null:

- For time effects: circularly shift each user's whole timeline by a random offset. This keeps each user's own rhythm and IP set but breaks synchrony between users.
- For structure: degree-preserving rewiring of the bipartite user–IP graph.

### E1 `[AGENT]` Build the weighted graph

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task E1: weighted user–user graph from the login export.

Inputs: <LOGIN_PATH> (hashed), data/labels/login_ip_labels.parquet.
Config: config/graph.yaml with rarity formula (adamic_adar |
resource_allocation), within-type rarity on/off, category factors per
network_type (use the placeholder values in section 6 of the plan),
tau0 in minutes, hub cap, prefix term on/off, supplier ID on/off
(default off).

Stage 1 — diagnostics only: degree distribution of IPs by network_type,
number of IPs above the hub cap and their share of logins, projected number
of user pairs. STOP and report.

Stage 2 — build the projected graph via (IP, time bucket) grouping, checking
neighbouring buckets so pairs across a bucket boundary aren't missed. Write
edges to data/graph/edges_<config_hash>.parquet with per-edge breakdown
(contribution by network_type). Report edge count, weight distribution, and
the largest connected component after dropping edges below
<MIN_WEIGHT, default 0>. STOP and report.
```

### E2 `[AGENT]` Clustering, null models and stability

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task E2: Leiden clustering with nulls.

Input: edges from E1. Using leidenalg (igraph):
1. Run CPM and modularity at resolutions <LIST>, 10 seeds each.
2. Build two nulls: (a) circular time-shift per user, rebuilt through E1
   with the same config; (b) degree-preserving rewiring of the bipartite
   graph. 10 null replicates each.
3. For each resolution: number of communities of size >= 3, their total
   internal weight, and the same statistics for the nulls. Flag communities
   whose internal weight exceeds the 95th percentile of null communities of
   similar size.
4. Seed stability: adjusted Rand index between seeds, and for flagged
   communities the share of members that stay together across seeds.

Output docs/findings/e2-clusters.md. STOP and report.
```

### E3 `[INVESTIGATE]` Has the picture changed?

**Question:** with labels, rarity and time weighting, does the giant component disappear, and does anything remain beyond the null?

**Expected outcome:** if H1 holds, the giant component is gone. A small number of communities may exceed the null, or none may.

**How to be certain:** comparison against the null at fixed resolution, stable across seeds. Both "communities beyond null" and "nothing beyond null" are legitimate results. Given the high-user filter (H3), the second is plausible and should be reported as such, not tuned away.

### E4 `[INVESTIGATE]` Sensitivity to category factors

**Method:** vary each category factor by ×0.5 and ×2, one at a time, and rerun E1–E2. Measure stability of the flagged communities (Jaccard overlap of membership with the baseline run).

**Expected outcome:** communities that reflect real structure persist across reasonable factor values.

**How to be certain:** overlap table across runs.

**Decision unlocked:** publish the factors together with the sensitivity result; drop any community that only appears under one setting.

---

## 7. Workstream F: risk scoring

### Background

**Entities.** The username is the main unit. The supplier ID is secondary, and its role depends on A2. Clusters from E add a coordination signal.

**Sub-scores, not one number.** Different threats look different, so compute separate sub-scores, each with reason codes, and only collapse them for sorting:

- **Takeover:** an established account's own pattern breaks (new networks, new devices, unusual hours, impossible travel).
- **Infrastructure:** logins come from hosting, listed or proxy-like networks, or hop across residential ISPs.
- **Coordination:** membership in a community that exceeds the null (E2).

Credential stuffing is **not** supported by this export if H3 holds, because stuffing victims are mostly filtered out. State that on every output.

**Normalisation.**

- Use rates per login rather than counts, because heavy users naturally accumulate more IPs and ASNs.
- Compare each user against their own history where possible. Heavy users have plenty of history, which is the one advantage of this dataset.
- Report percentiles against the high-user population always, and against the baseline (D1) only for features computable on session data.

**Features.** Thresholds below are starting values to tune, not conclusions.

| Feature | Definition | Sub-score | Caveat |
|---|---|---|---|
| `asn_switch_rate` | Share of consecutive logins where the ASN changes | Takeover | Home ↔ mobile alternation is normal; compare with own history |
| `type_switch_rate` | Share of consecutive logins where network type changes, excluding residential_fixed ↔ mobile | Infrastructure | Depends on label coverage |
| `residential_hopping` | Distinct residential/mobile ASNs beyond the user's top 2 by volume, per 100 logins | Infrastructure | Travel, moving house; check with country changes |
| `hosting_share` | Share of logins from hosting_cloud | Infrastructure | Some corporate VPNs exit through cloud providers |
| `listed_share` | Share of logins from vpn_proxy_listed, tor_exit or hostile_listed | Infrastructure | Consumer VPN use is common and legitimate |
| `ip_rotation_within_asn` | Distinct IPs (IPv6: /64) per login within the same ASN | Context only | High for mobile; not a risk feature on its own |
| `new_asn_recent` | ASNs in the recent window not seen in prior history | Takeover | Needs enough history |
| `new_supplier_id_recent` | Supplier IDs in the recent window not seen before | Takeover | Depends on A2 |
| `impossible_travel` | Consecutive login pairs above >500 km and >1000 km/h, excluding pairs where either end is mobile, VPN or hosting | Takeover | Geolocation error; compare with the supplier's own indicator |
| `timing_deviation` | Share of recent logins outside the user's usual hours | Takeover | Shift workers, travel |
| `regularity` | Coefficient of variation of inter-login intervals | Infrastructure | Scheduled legitimate jobs, if any |
| `mismatch_rate` | Device/network layer mismatches on uniquely matched sessions (C4) | Infrastructure | Matched subset is biased towards home broadband |
| `cluster_score` | Weight of the user's community relative to the null | Coordination | Only meaningful for communities flagged in E2 |

**Combining.** Convert each feature to a percentile. A sub-score is the mean of the top two feature percentiles within it, so a single noisy feature can't dominate. The rule is in config and published. Reason codes list every feature above the 95th percentile, with its value and percentile.

### F1 `[AGENT]` Feature computation

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task F1: per-user features.

Inputs: hashed login export, data/labels/login_ip_labels.parquet, and (phase
2 only) uniquely matched sessions from C4. Compute the features in section 7
of the plan ("Features") per username, for <RECENT_WINDOW> vs prior history.
Put every threshold (distance, speed, windows, top-k) in
config/features.yaml. Phase 1: skip mismatch_rate and cluster_score.

Tests: synthetic users with known answers for each feature, including
IPv6 users with rotating addresses inside one /64 (must count as one).

Output data/scores/features_<date>.parquet and docs/findings/f1-features.md
with per-feature distributions and null rates. STOP and report.
```

### F2 `[AGENT]` Scoring and reason codes

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task F2: sub-scores and reason codes.

From F1 output, compute percentiles per feature against the high-user
population (and against D1 baseline where the feature exists there). Compute
sub-scores (takeover, infrastructure, coordination) as the mean of the top 2
feature percentiles in each, rule in config/scoring.yaml. Reason codes:
every feature above the 95th percentile, with value and percentile.

Output data/scores/scores_<date>.parquet and docs/findings/f2-scores.md:
sub-score distributions, correlation between sub-scores, and the 20 users
with the highest sub-score in each category (hashed) with reason codes.
Do not adjust weights. STOP and report.
```

### F3 `[AGENT]` Synthetic injection test

Scenarios injected into a copy of the hashed data:

| ID | Scenario | Should score |
|---|---|---|
| S1 | Takeover via residential proxies: a real user's history continues, then 3–10 logins in a day from unrelated residential ASNs in other regions, with a new supplier ID | High takeover and infrastructure |
| S2 | Takeover via hosting: logins from a hosting ASN, new supplier ID, unusual hours | High takeover and infrastructure |
| S3 | Small ring: 5–20 synthetic accounts sharing a few rare hosting IPs within minutes | High coordination |
| S4 | Traveller: one country change, then home-like and mobile ISPs in the new country for days, same supplier ID | Low |
| S5 | Home + mobile: regular alternation between one fixed ISP and one mobile carrier | Low |
| S6 | University user: shares a Jisc/Janet IP with many others | Low |

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task F3: synthetic injection harness.

Build tests/injection/ that injects scenarios S1–S6 (section 7 of the plan)
into a COPY of the hashed login data, using synthetic IPs from documentation
ranges mapped to label rows of the required network type. Inject 20
instances of each scenario, rerun F1–F2 (and E1–E2 for S3), and report each
instance's percentile rank per sub-score, recall in the top 1% and top 50,
and how many benign instances (S4–S6) land in the top 1%.

Output docs/findings/f3-injection.md. STOP and report.
```

**Expected outcome:** S1–S3 rank high on the intended sub-score; S4–S6 do not.

**How to be certain:** recall and false-flag counts per scenario. Note the limit: synthetic scenarios encode our own assumptions, so this catches bugs and blind spots in the scoring logic, not real-world accuracy.

### F4 `[HUMAN]` Manual review

Review the top 50 users per sub-score. For each: plausibly benign, suspicious, or unclear, with one line of reasoning, and whether the reason codes explained the score. Record the time spent per user, since that's the real cost of the tool.

**Expected outcome:** a sense of precision at the top of each list, and which reason codes are most often misleading.

**How to be certain:** two passes at least a week apart on a subset, to check your own consistency.

### F5 `[INVESTIGATE]` Stability over time

**Method:** compute scores for two non-overlapping windows; compare rank correlation for users present in both, and the overlap of top 1% lists.

**Expected outcome:** moderate stability for infrastructure (habits persist), low for takeover (events are rare and short).

**How to be certain:** correlations with bootstrap intervals.

---

## 8. Workstream G: display

All views use real data, so they're rendered locally and not published.

1. **Overview:** logins per hour against distinct usernames, supplier IDs and ASNs per hour; network-type mix over time.
2. **Scatter:** per user, `asn_switch_rate` against logins (log scale), coloured by highest sub-score.
3. **Ranked table:** sub-scores with reason codes, filterable by sub-score.
4. **Per-user timeline:** lanes by network type, points coloured by ASN, impossible-travel jumps and supplier-ID changes marked.
5. **Network view:** per IP/prefix/ASN, external label, behavioural label, users over time. Mainly for checking label disagreements (B9).
6. **Cluster view:** communities flagged in E2, with members' timelines aligned.

### G1 `[AGENT]` Build the views

```text
Read section 0 of docs/plan-login-risk.md and follow the agent rules.

Task G1: local dashboard.

Build the six views in section 8 of the plan as a Quarto project under
dashboard/ (Plotly), reading only from data/scores/, data/graph/ and
data/labels/. Hashed identifiers only. Add dashboard/_site/ and any
rendered output to .gitignore. Render locally and report which views work,
render time, and file size. STOP and report.
```

### G2 `[HUMAN]` Decide what becomes public

A public openbotrisk page should most likely be the method plus a synthetic replication, with aggregate findings only if the governance questions in section 9 allow it and the source licences permit (B2).

---

## 9. Parked: data governance

Parked by decision on 2026-10-16. Not legal advice. Summary of the earlier discussion:

- IP addresses, device settings and usernames are each likely to be personal data under UK GDPR; combining them raises the risk level. Keyed hashing is pseudonymisation, which reduces risk but stays in scope.
- Per-user risk scoring is profiling. Data matching, large-scale profiling and tracking appear on the ICO's list of processing likely to need a DPIA (check the current list).
- The likely biggest issue is role and purpose: if the data comes from an organisation you're working for, you're probably its processor, and reusing the data for openbotrisk is a new purpose.

Gates that still apply while this is parked:

1. Before any bulk session pull: supplier terms confirmed (C1).
2. Never join usernames to names, emails or other identity data in the analysis environment.
3. Before anything is published: aggregates only with small-count suppression, or synthetic replication; source licences checked (B2).

---

## 10. Open questions

These would change the plan. Answers can go straight into this section.

1. **Repo:** where will the code live? This plan assumes a private working repo separate from the public openbotrisk site.
2. **Scale:** login export size (rows, users, date span) and session API volume per day, if known.
3. **IPv6:** roughly what share of traffic is IPv6? (A6 measures it.)
4. **Outcome field:** does the login export have success/failure or blocked status? (A1 Q3, A4.)
5. **Supplier ID:** do you know how it's derived? (A1 Q1, A2.)
6. **High users:** do you know the selection rule? (A1 Q2, A3.)
7. **Shared key:** does any session field match something in the login export besides IP and time? (A1 Q6.) This decides whether C4 can be verified.
8. **Device fields:** which are available (user agent, OS, screen, timezone, language…)? These set B7 and `mismatch_rate`.
9. **Supplier bot score:** do session records carry a bot score or classification? If so, it's a weak label for D3, F3 and F4, with the caveat that it reflects the supplier's own model.
10. **Compute:** local machine RAM and disk budget for Parquet storage.
11. **Purpose:** is the end goal an internal tool for this organisation, a public openbotrisk page, or both? This mainly affects section 9 and G2.
12. **Geolocation source:** which provider produced the export's country and ASN fields? (A1 Q4.) Mismatches with IPinfo in B4 are only interpretable if this is known.

---

## 11. References

Label sources:

- IPinfo Lite. https://ipinfo.io/lite
- ASdb. https://asdb.stanford.edu. Ziv, M. et al. (2021) "ASdb: A System for Classifying Owners of Autonomous Systems", ACM IMC.
- Spamhaus DROP lists, terms of use. https://www.spamhaus.org/drop/terms/ and FAQ https://www.spamhaus.com/faqs/drop/
- CAIDA AS Classification (discontinued). https://www.caida.org/data/as-classification/

Standards:

- RFC 5737, IPv4 address blocks reserved for documentation.
- RFC 3849, IPv6 address prefix reserved for documentation.
- RFC 8981, temporary address extensions for stateless address autoconfiguration in IPv6.

Methods (several already in the evidence register):

- Adamic, L. & Adar, E. (2003) "Friends and neighbors on the Web", *Social Networks* 25(3).
- Zhou, T., Lü, L. & Zhang, Y.-C. (2009) "Predicting missing links via local information", *European Physical Journal B* 71 (resource allocation index).
- Cao, Q. et al. (2014) "Uncovering large groups of active malicious accounts in online social networks" (SynchroTrap), ACM CCS.
- Blondel, V. et al. (2008) Louvain method, *J. Stat. Mech.*
- Traag, V., Waltman, L. & van Eck, N. (2019) "From Louvain to Leiden: guaranteeing well-connected communities", *Scientific Reports* 9.
- Fortunato, S. & Barthélemy, M. (2007) "Resolution limit in community detection", *PNAS* 104(1).

Legal context (parked):

- CJEU, *Breyer v Bundesrepublik Deutschland*, C-582/14 (2016).
- UK GDPR Art. 4(1), 4(4), 5(1)(b), 22; Recitals 26, 30, 47, 49.
