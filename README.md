# RoboSystems XBRL Holon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Convert SEC XBRL filings into `holon.jsonld` documents that render in the
[RoboSystems Holon Viewer](https://holon.robosystems.ai/).

## Installation

```bash
pip install robosystems-xbrl-holon
```

## Usage

```bash
# Build a holon.jsonld document from a specific filing
just holon-build 320193 0000320193-23-000106

# Fetch the latest filing for a ticker
just holon-fetch NVDA
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

### SEC User-Agent

SEC EDGAR requires a descriptive `User-Agent` on every request, or it throttles
you (empty responses / HTTP 429). Copy the template and set yours:

```bash
cp .env.example .env
# then edit SEC_GOV_USER_AGENT="Your Name your@email.com"
```

`.env` is loaded automatically by every command. Equivalently, `export
SEC_GOV_USER_AGENT="Your Name your@email.com"` or pass `--user-agent` per call.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

MIT © 2026 RFS LLC
