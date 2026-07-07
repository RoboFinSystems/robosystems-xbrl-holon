# RoboSystems XBRL Holon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Convert SEC XBRL filings into `holon.jsonld` documents that render in the RoboSystems holon viewer.

## Installation

```bash
pip install robosystems-xbrl-holon
```

## Usage

```bash
# Build a holon.jsonld document from a specific filing
holon build --cik 320193 --accno 0000320193-23-000106 -o report.holon.jsonld

# Fetch the latest filing for a ticker
holon fetch --ticker NVDA
```

> **Note:** SEC EDGAR requires a descriptive User-Agent for all requests. Set
> `XBRL_HOLON_USER_AGENT` (e.g. `"Your Name your@email.com"`) before running any
> command that reaches SEC.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

MIT © 2026 RFS LLC
