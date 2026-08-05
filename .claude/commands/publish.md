---
description: Monitor a release/publish run — diagnose failures, verify the package landed on PyPI.
argument-hint: '[run-id]'
---

Monitor a release and publish run — pinpoint why it failed, and confirm the version landed on PyPI in a usable state.

## How a release happens here

1. **`create-release.yml`** (dispatch) bumps the version on `main`, cuts `release/<version>`, and `tag-release.yml` tags it and cuts the GitHub Release.
2. **`publish.yml`** is triggered by **a push to `release/**`** — not by a merge and not by the tag.

So **merging to `main` publishes nothing.** The release-branch push is the publishing event.

## Scope & guardrails

- **`gh` reads are free; dispatching a release is not.** A PyPI version can be yanked but **never re-uploaded**, so a bad publish burns that version number permanently. Confirm the bump type and ref with the user; default to watching a run they already started.
- **Never bump `version` in `pyproject.toml` by hand** — the workflow owns it.
- **A CLI contract change is a downstream event.** Anyone scripting `holon build …` breaks on a renamed command or flag. Say so and stop rather than dispatching.

## 1. Find the run

```bash
gh run list --workflow=publish.yml --limit 5
gh run view <run-id>
gh run watch <run-id>
```

## 2. Pinpoint the failure

```bash
gh run view <run-id> --log-failed
```

- **Branch already exists** — a previous release run got partway; resolve the leftover `release/<version>` rather than re-dispatching blindly.
- **Build** — `just build-package` / `python -m build`. Packaging metadata problems surface here and nowhere in `just test-all`, which never builds a distribution.
- **Upload** — trusted publishing over OIDC; failures are usually PyPI-side publisher configuration, not code.
- **Version already on PyPI** — the publish is skipped rather than failing. If you expected one, the version wasn't bumped.

## 3. Verify it landed

```bash
curl -s https://pypi.org/pypi/robosystems-xbrl-holon/json | jq -r '.info.version'
```

Then confirm the artifact is usable, since packaging faults don't fail the upload:

```bash
pip download robosystems-xbrl-holon==<version> --no-deps -d /tmp/verify
unzip -l /tmp/verify/robosystems_xbrl_holon-<version>-*.whl | head -30
```

Check `py.typed` is present (its absence silently untypes the library for consumers) and that the vendored `_vendor/` files shipped — a missing vendored module fails only at import time on a user's machine.

Then the real check — the CLI actually runs:

```bash
uvx --from robosystems-xbrl-holon==<version> holon --help
```

## Output

Which workflow, what failed and where, the root cause, the re-run link, the verified published version, and whether the CLI runs from the published artifact. If nothing failed, say so.

$ARGUMENTS
