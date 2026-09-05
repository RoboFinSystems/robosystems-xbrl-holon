"""Parse: load a SEC XBRL filing with Arelle into the neutral ``XbrlModel``.

Two steps, one contract:

- :func:`load_model` builds a headless Arelle controller (inline-XBRL enabled)
  and returns the loaded ``ModelXbrl``.
- :func:`to_xbrl_model` walks that ``ModelXbrl`` into a single-filing
  :class:`xbrlkit.model.XbrlModel`.

:func:`close` releases the controller when done. A host with its own Arelle
controller calls :func:`register_sec_transforms` to get the SEC inline-XBRL
transforms this package vendors.
"""

from __future__ import annotations

from xbrlkit.parse.arelle_load import close, load_model, register_sec_transforms
from xbrlkit.parse.to_model import to_xbrl_model

__all__ = ["close", "load_model", "register_sec_transforms", "to_xbrl_model"]
