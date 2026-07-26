#!/usr/bin/env python
"""Convenience launcher so `bpc` works from any directory.

    python run.py <url>          -> CLI
    python run.py --web [opts]   -> local web UI
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        from bpc.web import main
        sys.exit(main(sys.argv[2:]))
    from bpc.cli import main
    sys.exit(main())
