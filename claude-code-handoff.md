# open-company-uk — agent handoff pack v2 (Claude Code)

Supersedes codex-handoff.md. Agent is Claude Code for now (Codex down); the constraints
are agent-agnostic. **New mechanism: put CLAUDE.md (supplied) in the repo root** — Claude
Code reads it automatically every session, so the standing lines no longer need pasting
into each prompt. Task prompts below are therefore shorter than the Codex versions; if
Codex returns, paste the CLAUDE.md content into its prompts manually.

## Status

| Item | State |
|---|---|
| Prompt A — officers + pagination | DONE (agent-reported; verify per review list below) |
| Prompt B — PSC fields + PSC_UNRESOLVED | DONE (agent-reported; verify below) |
| Severity `low` semantics | Patch supplied (severity-low.patch) — apply before next task |
| Pre-handoff live checks | Partially outstanding: 404-vs-empty-list on PSC endpoints, deprecated booleans, officers shape on a real 100+ officer PLC |
| Prompt C — Gazette | Still deferred pending your inspection of the Gazette API auth/terms |
| Phase 1.2 — late-filing reconstruction | Next design session with Claude (chat), NOT an agent task yet |

## Apply first (you, 2 minutes)

```bash
git apply severity-low.patch      # from repo root; or `patch -p1 < severity-low.patch`
ukcompany rules-doc               # regenerate docs/rules.md
cp CLAUDE.md .                    # into repo root; commit both
pytest && ruff check src tests
```

If a hunk fails (possible if the agent reflowed adjacent lines), the patch is small
enough to apply by hand — it only (a) rewrites the severity-semantics block in
generate_rules_md, (b) updates the severity comment on the Rule dataclass, (c) adds
`low:` to the summarise() breakdown in score.py.

## Verification list for A + B (you, before any new task)

1. `git diff --stat` vs branch point — scope matches the reports; confirm README.md and
   test_validate.py diffs predate the agent tasks (they do — they're from earlier steps).
2. Read `_fetch_paginated` — now shared under three endpoints, so bugs triple. Check it
   cannot spin on a 200-with-empty-items page mid-sequence.
3. Grep new fixtures for realistic-looking names (synthetic-only policy).
4. Live: old PLC with 100+ officers (pagination vs reality); record in AUDIT whether PSC
   endpoints 404 or return 200+empty for no-PSC companies — this decides
   psc_fetch_status semantics.
5. Spot-check psc_descriptions.yml yourself for the three PSC_UNRESOLVED trigger codes.

## Prompt C — Gazette winding-up petitions (unchanged: not yet written)

Still gated on your inspection of the Gazette data service (auth model, terms, join
quality to company numbers). Scope after you have looked at real notices.

## Prompt D — attribute export polish (optional, small, agent-ready now)

Use only if you want a low-risk task while deciding next steps:

```
Task: output ergonomics only — no new endpoints, no rule changes.
1. `ukcompany run` currently writes companies.csv with a key-union header. Pin a stable
   column order: identity fields first (company_number, company_name, company_status,
   company_type), then dates, then accounts/compliance, then officer counts, then PSC
   fields, then insolvency, then context — derive the order from FIELD_DOCS order where
   possible so the data dictionary and CSV read in the same sequence.
2. Add `--format parquet` to `ukcompany run` writing companies.parquet alongside the CSV
   ONLY if polars is installed (optional dependency `[parquet]` extra in pyproject);
   plain CSV path must keep zero new required dependencies.
3. Tests for column ordering and for graceful behaviour without polars installed.
Exit: pytest + ruff green; diff limited to score.py, cli.py, derive.py (ordering
helper), pyproject.toml, tests/.
```

## Phase 1.2 — what happens before it becomes a prompt

Design session in chat (Claude, not Claude Code): statutory deadline reconstruction —
first-accounts rule (21 months from incorporation vs 9 months from ARD period end),
private/public differences, historical regime changes, COVID-era extensions, and a table
of worked test cases (company shape -> expected deadline) that becomes the agent's test
spec. The agent implements against the worked cases; it does not research the rules.
Inputs already captured in the attribute table: ard_day, ard_month,
next_accounts_period_end, date_of_creation.

## Standing lines

Now live in CLAUDE.md (repo root). Highlights the agent sees every session: never
push/PR; judgement layer human-edited; fetched_at not now; synthetic fixtures only;
FIELD_DOCS + regenerated docs; AUDIT.md appended per task.
