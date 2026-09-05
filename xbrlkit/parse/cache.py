"""The Arelle schema cache: seed it, fill it, bundle it, check it.

A filing's DTS is a few hundred files from a handful of hosts, and two of
them (xbrl.org, w3.org) throttle a cold cache within a few dozen filings. The
answer is a warm cache before the first filing: a container image ships a
bundle and extracts it (:func:`seed`), a workstation fills its cache once
from the standard entry points (:func:`download`), and either can be packed
for the next machine (:func:`bundle`). Everything is written in Arelle's own
cache layout — ``<cache_dir>/<scheme>/<host>/<path>`` — so Arelle finds the
files without help, and :func:`cache_path` is that layout as a function.

``xbrlkit cache download | extract | bundle | status`` is the CLI over this
module.
"""

from __future__ import annotations

import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from xbrlkit.config import CONFIG, Config

try:  # Arelle's name for a URL that ends in "/"
  from arelle.WebCache import DIRECTORY_INDEX_FILE
except Exception:  # pragma: no cover
  DIRECTORY_INDEX_FILE = "!~DirectoryIndex~!"

# The hosts that have throttled a cold corpus run. A bundle built for a
# container should carry every file from these; the others (xbrl.sec.gov,
# xbrl.fasb.org) serve a warm-ish cache without complaint.
THROTTLED_HOSTS: tuple[str, ...] = ("www.w3.org", "www.xbrl.org", "xbrl.org")

# Files Arelle needs for any filing at all; their absence means the cache was
# never seeded, not that a taxonomy year is missing.
ESSENTIAL_URLS: tuple[str, ...] = (
  "https://www.w3.org/2001/xml.xsd",
  "https://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd",
  "https://www.xbrl.org/2003/xbrl-linkbase-2003-12-31.xsd",
)

# The XBRL core, inline XBRL, the data-type and role registries: every SEC
# filing's DTS reaches these, and they live on the throttled hosts.
CORE_ENTRY_POINTS: tuple[str, ...] = (
  "https://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd",
  "https://www.xbrl.org/2003/xbrl-linkbase-2003-12-31.xsd",
  "https://www.xbrl.org/2005/xbrldt-2005.xsd",
  "https://www.xbrl.org/2006/xbrldi-2006.xsd",
  "https://www.xbrl.org/2006/ref-2006-02-27.xsd",
  "https://www.xbrl.org/2013/inlineXBRL/xhtml-inlinexbrl-1_1.xsd",
  "https://www.xbrl.org/dtr/type/2020-01-21/types.xsd",
  "https://www.xbrl.org/dtr/type/2022-03-31/types.xsd",
  "https://www.xbrl.org/2020/extensible-enumerations-2.0.xsd",
  "https://www.xbrl.org/2023/calculation-1.1.xsd",
  "https://www.xbrl.org/lrr/role/negated-2009-12-16.xsd",
  "https://www.xbrl.org/lrr/role/net-2009-12-16.xsd",
  "https://www.xbrl.org/lrr/role/reference-2009-12-16.xsd",
)

# Per-year SEC and FASB taxonomies, by their entry-point schema. A year a
# taxonomy was not published for 404s and is reported, not fatal.
YEARLY_ENTRY_POINTS: tuple[str, ...] = (
  "https://xbrl.sec.gov/dei/{y}/dei-{y}.xsd",
  "https://xbrl.sec.gov/ecd/{y}/ecd-{y}.xsd",
  "https://xbrl.sec.gov/country/{y}/country-{y}.xsd",
  "https://xbrl.sec.gov/currency/{y}/currency-{y}.xsd",
  "https://xbrl.sec.gov/exch/{y}/exch-{y}.xsd",
  "https://xbrl.sec.gov/stpr/{y}/stpr-{y}.xsd",
  "https://xbrl.sec.gov/naics/{y}/naics-{y}.xsd",
  "https://xbrl.sec.gov/sic/{y}/sic-{y}.xsd",
  "https://xbrl.sec.gov/cyd/{y}/cyd-{y}.xsd",
  "https://xbrl.fasb.org/us-gaap/{y}/elts/us-gaap-{y}.xsd",
  "https://xbrl.fasb.org/srt/{y}/elts/srt-{y}.xsd",
)

DEFAULT_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025, 2026)


def entry_points(years: tuple[int, ...] | list[int] = DEFAULT_YEARS) -> list[str]:
  """The standard seed list: the core plus each year's SEC and FASB
  taxonomies."""
  urls = list(CORE_ENTRY_POINTS)
  for year in years:
    urls.extend(template.format(y=year) for template in YEARLY_ENTRY_POINTS)
  return urls


def cache_path(cache_dir: Path, url: str) -> Path:
  """Where Arelle keeps ``url``: ``<cache_dir>/<scheme>/<host>[/^port<n>]/<path>``.

  Mirrors ``WebCache.urlToCacheFilepath`` for the URLs a DTS uses (no user
  info; ``/`` separators). A URL ending in ``/`` maps to Arelle's directory
  index name.
  """
  parsed = urlparse(url)
  parts: list[str] = [parsed.scheme, parsed.hostname or ""]
  if parsed.port:
    parts.append(f"^port{parsed.port}")
  path = parsed.path
  if path.endswith("/") or not path:
    path = path + DIRECTORY_INDEX_FILE
  parts.extend(segment for segment in path.split("/") if segment)
  return Path(cache_dir).joinpath(*parts)


@dataclass
class CacheStatus:
  """What a cache directory holds."""

  cache_dir: Path
  files: int = 0
  schemas: int = 0
  by_host: dict[str, int] = field(default_factory=dict)
  missing_essentials: list[str] = field(default_factory=list)

  @property
  def seeded(self) -> bool:
    return not self.missing_essentials


def status(cache_dir: Path | None = None, config: Config = CONFIG) -> CacheStatus:
  """Count the cache's files per host and check the essentials are present."""
  root = Path(cache_dir) if cache_dir is not None else config.arelle_cache_dir
  result = CacheStatus(cache_dir=root)
  if not root.exists():
    result.missing_essentials = list(ESSENTIAL_URLS)
    return result
  for path in root.rglob("*"):
    if not path.is_file():
      continue
    rel = path.relative_to(root).parts
    if len(rel) < 3 or rel[0] not in ("http", "https"):
      continue
    result.files += 1
    result.by_host[rel[1]] = result.by_host.get(rel[1], 0) + 1
    if path.suffix == ".xsd":
      result.schemas += 1
  for url in ESSENTIAL_URLS:
    if not any(
      cache_path(root, candidate).exists() for candidate in _scheme_variants(url)
    ):
      result.missing_essentials.append(url)
  return result


@dataclass
class SeedReport:
  """What :func:`seed` wrote."""

  bundle: Path
  cache_dir: Path
  written: int = 0
  skipped: int = 0


def seed(
  bundle_path: Path, cache_dir: Path | None = None, config: Config = CONFIG
) -> SeedReport:
  """Extract a schema bundle into the cache, in Arelle's layout.

  Two bundle layouts are read: xbrlkit's, whose entries are
  ``<scheme>/<host>/<path>``; and the legacy one whose entries are
  ``cache/<host>/<path>`` (no scheme), which land under ``https``. Files
  already present are left alone.
  """
  root = Path(cache_dir) if cache_dir is not None else config.arelle_cache_dir
  root.mkdir(parents=True, exist_ok=True)
  report = SeedReport(bundle=Path(bundle_path), cache_dir=root)
  with tarfile.open(bundle_path, "r:*") as archive:
    for member in archive.getmembers():
      if not member.isfile():
        continue
      parts = [p for p in Path(member.name).parts if p not in ("", ".")]
      if parts and parts[0] == "cache":
        parts = parts[1:]
      if not parts:
        continue
      if parts[0] in ("http", "https"):
        target_parts = parts
      else:
        # Legacy layout: <host>/<path>; metadata files ride at the top.
        if len(parts) < 2 or "." not in parts[0]:
          report.skipped += 1
          continue
        target_parts = ["https", *parts]
      target = root.joinpath(*target_parts)
      if _is_outside(target, root):
        report.skipped += 1
        continue
      if target.exists() and target.stat().st_size > 0:
        report.skipped += 1
        continue
      handle = archive.extractfile(member)
      if handle is None:
        report.skipped += 1
        continue
      target.parent.mkdir(parents=True, exist_ok=True)
      with handle, open(target, "wb") as out:
        out.write(handle.read())
      report.written += 1
  return report


def bundle(
  out_path: Path,
  cache_dir: Path | None = None,
  hosts: tuple[str, ...] | list[str] | None = None,
  config: Config = CONFIG,
) -> int:
  """Pack the cache (or the given hosts' part of it) as a ``tar.gz`` whose
  entries are ``<scheme>/<host>/<path>``. Returns the number of files packed."""
  root = Path(cache_dir) if cache_dir is not None else config.arelle_cache_dir
  out_path = Path(out_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)
  wanted = set(hosts) if hosts else None
  count = 0
  with tarfile.open(out_path, "w:gz") as archive:
    for path in sorted(root.rglob("*")):
      if not path.is_file():
        continue
      rel = path.relative_to(root)
      if len(rel.parts) < 3 or rel.parts[0] not in ("http", "https"):
        continue
      if wanted is not None and rel.parts[1] not in wanted:
        continue
      archive.add(path, arcname=rel.as_posix())
      count += 1
  return count


@dataclass
class DownloadReport:
  """What :func:`download` resolved."""

  cache_dir: Path
  loaded: list[str] = field(default_factory=list)
  failed: dict[str, str] = field(default_factory=dict)
  files_before: int = 0
  files_after: int = 0

  @property
  def files_added(self) -> int:
    return self.files_after - self.files_before


def download(
  urls: list[str] | tuple[str, ...] | None = None,
  cache_dir: Path | None = None,
  *,
  timeout: int | None = None,
  config: Config = CONFIG,
) -> DownloadReport:
  """Fill the cache by loading each entry point through Arelle.

  Loading a schema resolves its whole DTS — every import and every linkbase
  it references — through the same cache layer a filing load uses (per-host
  spacing, ``Retry-After`` backoff), so what lands in the cache is exactly
  what a filing referencing that entry point will need. A 404 (a taxonomy
  year that was never published) is reported in ``failed`` and skipped.
  """
  from .arelle_load import _build_controller, close, load_state

  root = Path(cache_dir) if cache_dir is not None else config.arelle_cache_dir
  report = DownloadReport(cache_dir=root, files_before=status(root).files)
  cntlr = _build_controller(
    root,
    offline=False,
    timeout=config.arelle_timeout if timeout is None else timeout,
    config=config,
  )
  try:
    for url in urls or entry_points():
      state = load_state(cntlr)
      before = len(state.unresolved)
      try:
        mx = cntlr.modelManager.load(url)
      except Exception as exc:  # pragma: no cover - Arelle logs, rarely raises
        report.failed[url] = str(exc)
        continue
      if mx is None or getattr(mx, "modelDocument", None) is None:
        report.failed[url] = "not loaded"
      elif len(state.unresolved) > before:
        report.failed[url] = "unresolved: " + ", ".join(state.unresolved[before:])
      else:
        report.loaded.append(url)
      if mx is not None:
        try:
          mx.close()
        except Exception:
          pass
  finally:
    close(cntlr)
  report.files_after = status(root).files
  return report


def _scheme_variants(url: str) -> tuple[str, str]:
  if url.startswith("https://"):
    return (url, "http://" + url[len("https://") :])
  if url.startswith("http://"):
    return ("https://" + url[len("http://") :], url)
  return (url, url)


def _is_outside(target: Path, root: Path) -> bool:
  try:
    target.resolve().relative_to(root.resolve())
  except ValueError:
    return True
  return False


__all__ = (
  "CORE_ENTRY_POINTS",
  "DEFAULT_YEARS",
  "ESSENTIAL_URLS",
  "THROTTLED_HOSTS",
  "YEARLY_ENTRY_POINTS",
  "CacheStatus",
  "DownloadReport",
  "SeedReport",
  "bundle",
  "cache_path",
  "download",
  "entry_points",
  "seed",
  "status",
)
