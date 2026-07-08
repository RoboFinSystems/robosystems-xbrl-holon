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

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arelle import Cntlr, PluginManager

from robosystems_xbrl_holon.config import CONFIG

if TYPE_CHECKING:
  from arelle.ModelXbrl import ModelXbrl

# SEC inline-XBRL transformation registry. Formatted numeric/date facts in
# modern 10-K/10-Q filings reference transforms in this namespace.
SEC_IXT_NAMESPACE = "http://www.sec.gov/inlineXBRL/transformation/2015-08-31"

# The vendored EDGAR plugin tree — its ``transform`` module carries the SEC ixt
# registry (name↔code tables) that standalone arelle-release lacks.
_VENDOR_PLUGINS = Path(__file__).resolve().parents[1] / "_vendor" / "arelle_plugins"


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

  The SEC ``2015-08-31`` transforms (``stateprovnameen``, ``edgarprovcountryen``,
  ``numwordsen``, …) are **not** in standalone ``arelle-release`` — they live in
  the EDGAR plugin's ``transform`` module, which this package vendors at
  ``_vendor/arelle_plugins/EDGAR/transform`` (just the transform registry, not the
  matplotlib-backed renderer). Without them, SEC-formatted cover-page/DEI facts
  (state/country codes, some dates/booleans/word-numbers) parse to
  ``(ixTransformValueError)``.

  The plugin publishes its transforms through a ``ModelManager.LoadCustomTransforms``
  mount point that Arelle doesn't invoke in this headless load, so we register them
  directly into the namespace map Arelle resolves against
  (``FunctionIxt.ixtNamespaceFunctions[ns][localName]``, FunctionIxt.py:34).
  """
  try:
    from arelle import FunctionIxt
  except Exception:
    return
  if str(_VENDOR_PLUGINS) not in sys.path:
    sys.path.insert(0, str(_VENDOR_PLUGINS))
  try:
    from EDGAR.transform import loadSECtransforms  # type: ignore[import-not-found]

    custom: dict[Any, Any] = {}
    loadSECtransforms(custom)
    FunctionIxt.ixtNamespaceFunctions[SEC_IXT_NAMESPACE] = {
      qn.localName: fn for qn, fn in custom.items()
    }
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
