"""Synchronous, sleep-based rate limiter for SEC EDGAR requests.

SEC fair-access allows ~10 req/s; 5 req/s is the safer default (see
:mod:`robosystems_xbrl_holon.config`). This limiter simply spaces successive
requests by ``1 / per_sec`` seconds — proactive spacing, not reactive backoff.
"""

from __future__ import annotations

import time


class RateLimiter:
  """Spaces requests so at most ``per_sec`` fire per second.

  Call :meth:`wait` immediately before each request. It blocks just long
  enough to keep consecutive calls ``1 / per_sec`` seconds apart.
  """

  def __init__(self, per_sec: float = 5.0) -> None:
    self.per_sec: float = per_sec
    self._interval: float = 1.0 / per_sec if per_sec > 0 else 0.0
    self._last: float = 0.0

  def wait(self) -> None:
    """Block until at least ``1 / per_sec`` seconds have passed."""
    if self._interval <= 0:
      return
    now = time.monotonic()
    delay = self._last + self._interval - now
    if delay > 0:
      time.sleep(delay)
    self._last = time.monotonic()
