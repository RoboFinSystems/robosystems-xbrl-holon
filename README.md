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
just holon-build 320193 0000320193-23-000106

# Fetch the latest filing for a ticker
just holon-fetch NVDA
```

> **Note:** SEC EDGAR requires a descriptive User-Agent for all requests. Set
> `SEC_GOV_USER_AGENT` (e.g. `"Your Name your@email.com"`) in your .env before
> running any command that reaches SEC.gov.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

MIT © 2026 RFS LLC
