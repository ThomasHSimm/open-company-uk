# CLAUDE.md — standing instructions for agent sessions in this repo

Read README.md, docs/plan.md, docs/rules.md and docs/data-dictionary.md before making
changes. This file states the non-negotiables that apply to every task.

## Git discipline
- Work on the current branch only. Never push. Never open a PR. The maintainer reviews
  locally and handles all pushes/merges.
- Keep diffs scoped to the task. If a needed change falls outside the stated file scope,
  make it minimally and flag the deviation explicitly in your summary and in docs/AUDIT.md.

## The judgement layer is human-edited
- Do not modify existing rules, severities, severity semantics, SOLVENT_CASE_TYPES, or
  EXCLUDED_STATUSES without explicit instruction naming the change.
- Severity grades the SERIOUSNESS of the recorded state (high / medium / low / info), not
  confidence in it. Confidence belongs in evidence strings and caveats.
- No composite score, anywhere, ever, without explicit instruction.

## Code conventions
- ruff, line length 100 (pyproject.toml); pytest; src layout, package `ukcompany`.
- .get() every field from API JSON; tolerate absence — older records are sparse.
- Elapsed-time attributes compute against the cached response's fetched_at, never "now".
- Methodological constants live in code with comments; runtime config in
  config/settings.yaml; API key ONLY via CH_API_KEY env (or .env, gitignored).
- Follow the cache envelope pattern in cache.py exactly; paginated endpoints merge all
  pages into one envelope per company per endpoint.

## Tests and data protection
- No network access in tests. All fixtures synthetic — invented names only, never real
  officer/PSC/company data beyond public company numbers.
- Cached 404 is a meaningful result, not an error.
- CI runs pytest + ruff; keep both green before declaring done.

## Documentation invariants
- Register every new derived attribute in FIELD_DOCS (derive.py) with tier, source,
  definition, caveats.
- docs/rules.md and docs/data-dictionary.md are GENERATED (`ukcompany rules-doc`,
  `ukcompany data-dict`) — never hand-edit them; regenerate after relevant changes.
- Append implementation notes and any assumptions needing live verification to
  docs/AUDIT.md at the end of every task.
