"""humanize_en.cli — command-line interface.

The ``humanize-en`` console script (declared in ``pyproject.toml``
under ``[project.scripts]``) dispatches to :func:`humanize_en.cli.main.main`.
The CLI is a thin wrapper around the top-level convenience API
(:func:`humanize_en.score`, :func:`humanize_en.postprocess_humanize`,
:func:`humanize_en.judge`), itself thin shims over ``humanize_core``.

Subcommands:

- ``humanize-en detect FILE``      — rule + n-gram + combined scoring
- ``humanize-en polish FILE``      — LLM rewrite of AI tells
- ``humanize-en judge FILE``       — LLM final-review verdict
- ``humanize-en providers``        — list auto-detectable LLM providers
- ``humanize-en ui``               — launch the web UI (``humanize-core[ui]``)

The module is **deliberately kept parallel** to
``humanize_zh.cli.main`` so that contributors updating one plugin's
CLI know where to look in the other. When in doubt, diff them.
"""

from __future__ import annotations

from .main import main

__all__ = ["main"]
