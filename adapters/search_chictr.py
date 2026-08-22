#!/usr/bin/env python3
"""search_chictr.py - China ChiCTR search (delegates to the unified Coze endpoint).

ChiCTR is the WHO primary registry for China covering academic / investigator-
initiated trials (distinct from CDE, which covers drug trials). It has NO public
API and blocks automated access. It is served by the SAME unified Coze workflow
(source="chictr"), extended alongside WHO ICTRP / CDE / ISRCTN / DRKS. This thin
wrapper forwards to search_ictrp.py --source chictr, sharing the ICTRP Bearer
token and the unified endpoint — no separate endpoint or token to provision.

The unified endpoint must be configured to serve source="chictr" before real
records are returned. No network I/O unless --run (safe preview).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_ictrp  # noqa: E402


if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--source", "chictr"] + sys.argv[1:]
    search_ictrp.main()
