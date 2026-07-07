"""Load a SEC XBRL filing with Arelle into a ``ModelXbrl``.

A platform-free distillation of the robosystems SEC adapter's ``ArelleClient``
(``adapters/sec/client/arelle.py``). It keeps the parts that matter for a
faithful parse — the inline-XBRL document-set plugin, SEC ixt transform
registration, and a hybrid (cache-first, fetch-on-miss) WebCache — and drops
the adapter's pre-baked schema bundle, EFM validation, and rate-limit retry
wrappers, which are deployment concerns.

Usage::

    mx = load_model(source)
    model = to_xbrl_model(mx, filing)
    close(mx.modelManager.cntlr)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from arelle import Cntlr, PluginManager

from robosystems_xbrl_holon.config import CONFIG

if TYPE_CHECKING:
  from arelle.ModelXbrl import ModelXbrl

# SEC inline-XBRL transformation registry. Formatted numeric/date facts in
# modern 10-K/10-Q filings reference transforms in this namespace.
SEC_IXT_NAMESPACE = "http://www.sec.gov/inlineXBRL/transformation/2015-08-31"


def load_model(source: str | Path, cache_dir: Path | None = None) -> ModelXbrl:
  """Load an XBRL (inline or classic) document and return its ``ModelXbrl``.

  ``source`` may be a local path or an ``http(s)://`` URL. On first run Arelle
  fetches and caches the referenced DTS schemas under ``cache_dir`` (defaults
  to :attr:`Config.arelle_cache_dir`); subsequent runs read from cache.

  The controller stays open — its C-extension model is live and the caller
  owns it. Pass ``mx.modelManager.cntlr`` to :func:`close` when done.
  """
  cntlr = _build_controller(cache_dir)
  mx = cntlr.modelManager.load(str(source))
  if mx is None or getattr(mx, "modelDocument", None) is None:
    close(cntlr)
    raise RuntimeError(f"Arelle failed to load an XBRL document from: {source}")
  return mx


def close(cntlr: Any) -> None:
  """Close an Arelle controller, releasing its model and file handles."""
  if cntlr is None:
    return
  try:
    cntlr.close()
  except Exception:
    pass


def _build_controller(cache_dir: Path | None) -> Any:
  """Construct a headless Arelle controller wired for inline SEC XBRL."""
  resolved = Path(cache_dir) if cache_dir is not None else CONFIG.arelle_cache_dir
  resolved.mkdir(parents=True, exist_ok=True)

  cntlr = Cntlr.Cntlr(
    hasGui=False,
    logFileName="logToBuffer",
    logFileMode="w",
    uiLang=None,
    disable_persistent_config=True,
  )

  _enable_inline_xbrl(cntlr)
  _configure_webcache(cntlr, resolved)
  return cntlr


def _enable_inline_xbrl(cntlr: Any) -> None:
  """Load the inline-XBRL document-set plugin and SEC ixt transforms.

  Without ``inlineXbrlDocumentSet`` Arelle treats an inline 10-K as plain HTML
  and every fact silently drops, so this wiring is load-bearing for modern
  filings.
  """
  PluginManager.init(cntlr, loadPluginConfig=False)
  try:
    PluginManager.addPluginModule("inlineXbrlDocumentSet")
  except Exception:
    pass
  _register_sec_transforms()
  try:
    PluginManager.reset()
  except Exception:
    pass


def _register_sec_transforms() -> None:
  """Register the SEC inline-XBRL transformation functions.

  The SEC ``2015-08-31`` transforms (duryear, stateprovnameen, …) ship with
  Arelle's EDGAR plugin. We attempt to load it so SEC-formatted inline facts
  parse fully; a standalone ``arelle-release`` install without the plugin
  falls back to Arelle's built-in ixt registries (``FunctionIxt``), which
  cover the standard transformation registries the bulk of modern inline
  filings reference.
  """
  try:
    from arelle import FunctionIxt  # noqa: F401  (import registers registries)
  except Exception:
    return
  try:
    PluginManager.addPluginModule("EDGAR/transform")
  except Exception:
    pass


def _configure_webcache(cntlr: Any, cache_dir: Path) -> None:
  """Point the WebCache at ``cache_dir`` in hybrid (online) mode."""
  webcache = getattr(cntlr, "webCache", None)
  if webcache is None:
    return
  webcache.cacheDir = str(cache_dir)
  webcache.workOffline = False
  webcache.httpsRedirect = True
