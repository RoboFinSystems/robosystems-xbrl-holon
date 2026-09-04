---
description: Run the full test and code-quality gate, fixing failures to green.
argument-hint: '[test-path]'
---

Run `just test-all` and systematically fix all failures to achieve 100% completion.

## Timeouts

Use `timeout: 600000` on Bash calls for `just test-all` — the default 2-minute Bash timeout is too short once network-touching tests are included.

## Strategy

1. **Run the full gate first**, filtering for signal (below).
2. **Fix in the order it runs**: `just test` (pytest) → `just format` → `just lint` → `just typecheck`.
3. **Iterate on the failing layer only** — `uv run pytest path/to/test.py` for the fastest loop.
4. **Stop when green.** Don't re-run to "confirm."

## What `just test-all` runs

```
just test → just format → just lint → just typecheck
```

Only the first stage emits a pytest summary. A ruff or basedpyright failure surfaces as a recipe-failure line with no `failed` count — so **a green pytest count alone is not proof the gate passed**.

`just format` is `ruff format` (auto-write), so the gate **mutates the working tree**. Check `git status` afterwards and stage what it rewrote; the pre-commit hook runs check-only variants and will fail on exactly those files.

**Everything runs through `uv run`.** Bare `pytest`, `ruff`, or `python` use the wrong environment.

## Output Handling

```
just test-all 2>&1 | grep -E "passed|failed|error:|FAILED|warnings summary|^= " | tail -20
```

## Notes

- **Conversion tests are filing-specific.** A parse fix verified against one filing is barely verified — SEC XBRL varies enormously between filers and years. Add a fixture for the filing that motivated the change.
- **Network-touching tests are a trap.** Anything hitting EDGAR depends on the SEC User-Agent being configured and on the SEC being reachable and not rate-limiting you. A failure there is usually environmental, not a code bug — check before "fixing" it.
- `xbrlkit/_vendor/` is vendored third-party code. Don't reformat or refactor it to make a lint pass; exclude it or fix the config.
- Never bump `version` in `pyproject.toml` to make anything pass.

## Goal

100% pass on `just test-all` with no errors of any kind.

$ARGUMENTS
