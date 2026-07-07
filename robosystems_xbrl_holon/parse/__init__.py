"""Parse: load a SEC XBRL filing with Arelle into the neutral ``XbrlModel``.

Two steps, one contract:

- :func:`load_model` builds a headless Arelle controller (inline-XBRL enabled)
  and returns the loaded ``ModelXbrl``.
- :func:`to_xbrl_model` walks that ``ModelXbrl`` into a single-filing
  :class:`robosystems_xbrl_holon.model.XbrlModel`.

:func:`close` releases the controller when done.
"""

from __future__ import annotations

from robosystems_xbrl_holon.parse.arelle_load import close, load_model
from robosystems_xbrl_holon.parse.to_model import to_xbrl_model

__all__ = ["close", "load_model", "to_xbrl_model"]
