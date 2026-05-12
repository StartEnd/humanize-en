"""Enable ``python -m humanize_en.cli`` alongside the ``humanize-en`` script.

``pip install humanize-en`` installs a ``humanize-en`` console script
that points at :func:`humanize_en.cli.main.main`. That entry point is
only available once the package is properly installed (editable or
otherwise). For quick local development — or for anyone who
prefers to avoid the script stub — ``python -m humanize_en.cli``
is the equivalent incantation and always works.
"""

from __future__ import annotations

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
