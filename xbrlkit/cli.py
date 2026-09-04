"""Command-line interface — a SEC filing to a portable report document.

    xbrlkit build --cik 320193 --accno 0000320193-23-000106  # -> output/<accno>.holon.jsonld
    xbrlkit build --cik 320193 --accno … --format tavi       # -> output/<accno>.tavi.json
    xbrlkit fetch --ticker NVDA --form 10-K --n 1            # -> output/

Wires the three layers: ``edgar`` (fetch) -> ``parse`` (Arelle -> XbrlModel) ->
``serialize`` (XbrlModel -> a holon or a Tavi compiled model).

``--format tavi`` writes a second sidecar, ``<accession>.tavi.gaps.json``: what
the filing carries that Project Tavi has nowhere to put. That file is the point
of the Tavi projection, not a by-product of it.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from .config import Config
from .edgar import EdgarClient, download_filing
from .model import FilingMeta, XbrlModel
from .parse import close, load_model, to_xbrl_model
from .serialize import to_holon, to_tavi_report

# Generated documents land here by default — a git-tracked folder whose contents
# are git-ignored (see output/.gitignore). Relative to the working directory.
DEFAULT_OUTPUT_DIR = Path("output")

FORMATS = ("holon", "tavi", "both")
SUFFIXES = {"holon": ".holon.jsonld", "tavi": ".tavi.json"}


def _parse_date(value: str | None) -> date | None:
  if not value:
    return None
  try:
    return date.fromisoformat(value)
  except ValueError:
    return None


def _write_outputs(model: XbrlModel, out_path: Path, fmt: str, named: bool) -> None:
  """Write the requested projection(s) of ``model``.

  A single format with an explicit ``-o`` writes exactly that path, unchanged
  from before ``--format`` existed. Only ``--format both`` has to derive a stem,
  because one parse then produces two documents and they cannot share a name.
  """
  out_path.parent.mkdir(parents=True, exist_ok=True)
  stem = out_path.name
  for suffix in SUFFIXES.values():
    stem = stem.removesuffix(suffix)
  exact = out_path if named and fmt != "both" else None

  wanted = ("holon", "tavi") if fmt == "both" else (fmt,)
  for name in wanted:
    target = exact or out_path.parent / f"{stem}{SUFFIXES[name]}"
    if name == "holon":
      target.write_text(to_holon(model))
      print(f"wrote {target}")
    else:
      document, gaps = to_tavi_report(model)
      target.write_text(json.dumps(document, indent=2, default=str))
      gaps_path = out_path.parent / f"{stem}.tavi.gaps.json"
      gaps_path.write_text(json.dumps(gaps.to_dict(), indent=2, default=str))
      print(f"wrote {target}")
      against_model = len(gaps.item_types_without_builtin) + len(
        gaps.dropped_period_semantics
      )
      print(f"wrote {gaps_path}  ({against_model} findings against the model)")


def _build_one(
  client: EdgarClient,
  cik: str,
  accession: str,
  out_path: Path,
  cache_dir: Path,
  fmt: str = "holon",
  named: bool = False,
) -> XbrlModel:
  """Fetch one filing, parse it, and write the requested projection(s)."""
  ref = client.get_filing_ref(cik, accession)
  info = client.company_info(cik)
  with tempfile.TemporaryDirectory() as tmp:
    target = download_filing(client, cik, accession, Path(tmp))
    mx = load_model(target, cache_dir=cache_dir)
    try:
      filing = FilingMeta(
        accession=accession,
        cik=str(int(cik)).zfill(10),
        form=ref.form or None,
        filing_date=_parse_date(ref.filing_date),
      )
      model = to_xbrl_model(
        mx,
        filing,
        entity_name=info.name,
        entity_ein=info.ein,
        entity_ticker=info.ticker,
      )
    finally:
      close(mx.modelManager.cntlr)
  _write_outputs(model, out_path, fmt, named)
  print(f"  ({len(model.facts)} facts, {len(model.networks)} networks)")
  return model


def _config_from_args(args: argparse.Namespace) -> Config:
  if getattr(args, "user_agent", None):
    return Config(user_agent=args.user_agent)
  # Fresh Config() re-reads os.environ after main()'s load_dotenv(), so a
  # SEC_GOV_USER_AGENT set in .env is honored (the module-level CONFIG was
  # frozen at import, before the .env was loaded).
  return Config()


def _cmd_build(args: argparse.Namespace) -> int:
  config = _config_from_args(args)
  client = EdgarClient(config=config)
  out = Path(args.out) if args.out else DEFAULT_OUTPUT_DIR / args.accno
  _build_one(
    client,
    args.cik,
    args.accno,
    out,
    config.arelle_cache_dir,
    args.format,
    named=bool(args.out),
  )
  return 0


def _cmd_query(args: argparse.Namespace) -> int:
  from .query import fact_grid, load_holon

  graph = load_holon(args.infile)
  rows = fact_grid(
    graph,
    elements=args.element or None,
    periods=args.period or None,
    period_type=args.period_type,
  )
  for r in rows:
    print(f"{r.end_date or '':<12} {r.qname:<55} {r.value:>20,.4f}  {r.measure or ''}")
  print(f"({len(rows)} consolidated facts)", file=sys.stderr)
  return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
  config = _config_from_args(args)
  client = EdgarClient(config=config)
  cik = client.ticker_to_cik(args.ticker)
  filings = client.list_filings(cik, forms=[args.form] if args.form else None)
  if not filings:
    print(f"no {args.form or 'matching'} filings for {args.ticker}", file=sys.stderr)
    return 1
  out_dir = Path(args.out)
  out_dir.mkdir(parents=True, exist_ok=True)
  for ref in filings[: args.n]:
    _build_one(
      client,
      cik,
      ref.accession,
      out_dir / ref.accession,
      config.arelle_cache_dir,
      args.format,
    )
  return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="xbrlkit",
    description="Work with XBRL filings above Arelle: one parse, portable models.",
  )
  parser.add_argument(
    "--user-agent",
    help="SEC User-Agent (else $SEC_GOV_USER_AGENT). Must identify you with contact info.",
  )
  sub = parser.add_subparsers(dest="command", required=True)

  b = sub.add_parser("build", help="Build one filing by CIK + accession number.")
  b.add_argument("--cik", required=True, help="CIK (zero-padded or bare).")
  b.add_argument(
    "--accno", required=True, help="Accession number, e.g. 0000320193-23-000106."
  )
  b.add_argument(
    "-o",
    "--out",
    default=None,
    help="Output path (default: output/<accession>.holon.jsonld).",
  )
  b.add_argument(
    "--format",
    choices=FORMATS,
    default="holon",
    help="Projection to write (default holon). 'tavi' also writes a .tavi.gaps.json.",
  )
  b.set_defaults(func=_cmd_build)

  f = sub.add_parser("fetch", help="Fetch N filings for a ticker.")
  f.add_argument("--ticker", required=True, help="Ticker symbol, e.g. NVDA.")
  f.add_argument("--form", default="10-K", help="Form type filter (default 10-K).")
  f.add_argument(
    "--n", type=int, default=1, help="Number of most-recent filings (default 1)."
  )
  f.add_argument(
    "-o",
    "--out",
    default=str(DEFAULT_OUTPUT_DIR),
    help="Output directory (default: output/).",
  )
  f.add_argument(
    "--format",
    choices=FORMATS,
    default="holon",
    help="Projection to write (default holon). 'tavi' also writes a .tavi.gaps.json.",
  )
  f.set_defaults(func=_cmd_fetch)

  q = sub.add_parser(
    "query", help="Query consolidated facts in a holon.jsonld (in-memory SPARQL)."
  )
  q.add_argument("--in", dest="infile", required=True, help="Path to a holon.jsonld.")
  q.add_argument(
    "--element", action="append", help="Element qname filter, e.g. us-gaap:Assets."
  )
  q.add_argument(
    "--period", action="append", help="Period end date YYYY-MM-DD (repeatable)."
  )
  q.add_argument(
    "--period-type",
    choices=["instant", "annual", "quarterly"],
    dest="period_type",
    help="Restrict to instant / annual-duration / quarterly-duration facts.",
  )
  q.set_defaults(func=_cmd_query)
  return parser


def main(argv: list[str] | None = None) -> int:
  load_dotenv()  # load SEC_GOV_USER_AGENT (and other overrides) from a local .env
  parser = build_parser()
  args = parser.parse_args(argv)
  try:
    return args.func(args)
  except Exception as exc:  # surface a clean message, not a traceback, to the CLI user
    print(f"error: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
