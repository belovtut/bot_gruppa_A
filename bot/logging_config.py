"""Centralized logging setup for the bot process."""
from __future__ import annotations

import logging
import sys
from typing import TextIO


def setup_logging(
    level: int = logging.INFO,
    *,
    stream: TextIO | None = None,
) -> None:
    """Configure root logging once (idempotent for repeated calls in tests)."""
    stream = stream or sys.stdout
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=stream,
        force=False,
    )
