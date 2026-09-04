# xbrlkit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Work with XBRL filings above [Arelle](https://arelle.org): fetch a filing, parse
it **once** into a neutral typed model, and project that model into whichever
portable representation you need.

```
EDGAR ──▶ Arelle ──▶ XbrlModel ──┬──▶ holon.jsonld   (RDF / JSON-LD)
                                 ├──▶ Tavi           (compiled model)
                                 ├──▶ xBRL-JSON      (OIM)
                                 └──▶ …
```

Arelle stays the parser — nobody should reimplement DTS resolution. What it does
not give you is anything ergonomic to *hold*: `ModelXbrl` is a large mutable
object graph tied to a controller you have to close. `XbrlModel` is the answer to
that — stateless, single-filing, lossless, and the waist every projection hangs
off.

**The one architectural rule:** everything goes through `XbrlModel`. A feature
that reaches into Arelle's `ModelXbrl` directly is bypassing the waist, and that
is the change that turns a kit into a junk drawer.

## Projections

| Target | Status | Notes |
| --- | --- | --- |
| **holon** (`.holon.jsonld`) | shipped | RDF/JSON-LD, renders in the [Holon Viewer](https://holon.robosystems.ai/) |
| **Tavi** (`.tavi.json`) | shipped | [Project Tavi](https://www.xbrl.org/Specification/tavi/PWD-2026-09-01/tavi-PWD-2026-09-01.html) compiled model, PWD-2026-09-01 |
| **OIM** (`.oim.json`) | shipped | xBRL-JSON, checked fact-for-fact against Arelle's own writer |
| property graph / Parquet | planned | see `model.py` |

The OIM projection is the one with a **reference implementation** to check
against: Arelle's `saveLoadableOIM` writes the same document from the same
filing. A second writer is redundant as a feature — its value is that every
difference is a fidelity bug in the parse or the model, and those same bugs are
otherwise silent in the holon and Tavi outputs, which have nothing to check
them. Current parity is every fact on 3M FY2024 (3,150) and Boeing FY2024
(2,688), and all but one on Microsoft FY2024 (1,855 of 1,856); footnotes are
the one construct the model does not carry.

Tavi is a **public working draft** and its name is explicitly a working title,
so treat that projection as tracking a moving target. `--format tavi` also
writes a `.tavi.gaps.json` sidecar recording what the filing carries that the
model has nowhere to put — that file is the point of the projection, not a
by-product of it.

## Install

### As a package

```bash
pip install xbrlkit
```

Exposes the `xbrlkit` CLI (`xbrlkit build …`, `xbrlkit fetch …`, `xbrlkit query …`)
and the library — use this to consume it from another project. Set your SEC
User-Agent via the environment (see [SEC User-Agent](#sec-user-agent)).

### From source (development)

```bash
# Install the toolchain
brew install uv just

# Install dependencies and provision .env from the template
just install
```

`just install` creates `.env` from `.env.example` on first run — then set your
SEC User-Agent in it.

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
xbrlkit build --cik 320193 --accno 0000320193-23-000106

# Fetch the latest filing for a ticker (-> ./output/)
xbrlkit fetch --ticker NVDA

# Query consolidated facts in a built holon (in-memory SPARQL)
xbrlkit query --in output/0000320193-23-000106.holon.jsonld --element us-gaap:Assets
```

From a source checkout, `just` wraps the same CLI as a shorthand:
`just build 320193 0000320193-23-000106` and `just fetch NVDA`.

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
