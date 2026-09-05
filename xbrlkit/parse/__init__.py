"""Parse: load a SEC XBRL filing with Arelle into the neutral ``XbrlModel``.

Two steps, one contract:

- :func:`load_model` builds a headless Arelle controller (inline-XBRL enabled,
  the DTS served cache-first with per-host spacing and ``Retry-After``
  backoff) and returns the loaded ``ModelXbrl`` — or raises
  :class:`DtsResolutionError` when part of the DTS could not be resolved.
- :func:`to_xbrl_model` walks that ``ModelXbrl`` into a single-filing
  :class:`xbrlkit.model.XbrlModel`.

:func:`close` releases the controller when done. A host with its own Arelle
controller calls :func:`configure_webcache` to put the same cache policy on
it and :func:`register_sec_transforms` to get the SEC inline-XBRL transforms
this package vendors. The cache itself — seeding from a bundle, filling from
the standard entry points, packing for another machine — is
:mod:`xbrlkit.parse.cache`.
"""

from __future__ import annotations

from xbrlkit.parse.arelle_load import (
  DtsResolutionError,
  LoadState,
  close,
  configure_webcache,
  load_model,
  load_state,
  register_sec_transforms,
)
from xbrlkit.parse.to_model import to_xbrl_model

__all__ = [
  "DtsResolutionError",
  "LoadState",
  "close",
  "configure_webcache",
  "load_model",
  "load_state",
  "register_sec_transforms",
  "to_xbrl_model",
]
