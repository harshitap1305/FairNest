"""FairNest policy simulator package (wires directly to backend allocator & fairness core)."""

from __future__ import annotations

import os
import sys

_BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
