# RoboSystems XBRL Holon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Convert SEC XBRL filings into `holon.jsonld` documents that render in the
[RoboSystems Holon Viewer](https://holon.robosystems.ai/).

## Install

```bash
# Install the toolchain
brew install uv just

# Install dependencies and provision .env from the template
just install
```

`just install` creates `.env` from `.env.example` on first run — then set your
SEC User-Agent in it (see [SEC User-Agent](#sec-user-agent)). It exposes the
`holon` CLI (`holon build …`, `holon fetch …`, `holon query …`).

> Not yet published. Once it's on PyPI, you'll be able to `pip install
> robosystems-xbrl-holon` to use it as a dependency in another project.

## SEC User-Agent

SEC EDGAR requires a descriptive `User-Agent` on every request, or it throttles
you (empty responses / HTTP 429). `just install` already created your `.env` —
set your details there:

```bash
# .env
SEC_GOV_USER_AGENT="Your Name your@email.com"
```

`.env` is loaded automatically by every command. Outside the `just` workflow,
`export SEC_GOV_USER_AGENT="Your Name your@email.com"` or pass `--user-agent`.

## Usage

```bash
# Build a holon.jsonld from a specific filing (-> ./output/)
just holon-build 320193 0000320193-23-000106

# Fetch the latest filing for a ticker (-> ./output/)
just holon-fetch NVDA
```

Or call the `holon` CLI directly:

```bash
holon build --cik 320193 --accno 0000320193-23-000106
holon fetch --ticker NVDA
```

## View & explore

Built holons render in the **RoboSystems Holon Viewer** — a browser-based reader
that renders the financial statements and lets you ask questions of the report
with AI:

- **Hosted:** <https://holon.robosystems.ai/> — open a `holon.jsonld` and explore
  the statements, notes, and dimensional facts, or chat with the report.
- **Source:** <https://github.com/RoboFinSystems/robosystems-holon-viewer> — run
  it locally or self-host.

The viewer reads a holon entirely client-side, so a single `holon.jsonld` is a
complete, portable, self-describing report.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

MIT © 2026 RFS LLC
