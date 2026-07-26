"""Command-line entry point.

    python -m bpc <poe.ninja build URL>
    python -m bpc            # then paste the URL when prompted
"""
import argparse
import sys

from . import __version__, engine, poeninja, report


def _force_utf8() -> None:
    # Windows consoles default to cp1252 and choke on item names (e.g. Cyrillic account
    # names) and box-drawing/arrow glyphs. Make stdout/stderr tolerant.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None) -> int:
    _force_utf8()
    p = argparse.ArgumentParser(
        prog="bpc",
        description="Estimate the cost of a PoE1 build from a poe.ninja character link.")
    p.add_argument("url", nargs="?",
                   help="poe.ninja character link, Path of Building code, or pobb.in link")
    p.add_argument("--league", help="override the trade league (e.g. 'Standard')")
    p.add_argument("--status", default="online",
                   choices=["online", "any", "onlineleague", "available", "securable"],
                   help="listing status to search (default online)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p.add_argument("--fresh", "--refresh", dest="refresh", action="store_true",
                   help="fresh pull: ignore cached data/prices and fetch everything fresh")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")
    p.add_argument("--version", action="version", version=f"bpc {__version__}")
    args = p.parse_args(argv)

    url = args.url
    if not url:
        try:
            url = input("Paste poe.ninja link / PoB code / pobb.in link: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 1
    if not url:
        print("No URL provided.", file=sys.stderr)
        return 2

    verbose = not args.quiet
    progress = (lambda m: print(f"  {m}", file=sys.stderr, flush=True)) if verbose else None
    try:
        meta, results, pricer, league = engine.run_estimate(
            url, league=args.league, refresh=args.refresh, progress=progress,
            status=args.status)
    except (poeninja.PoeNinjaError, engine.EstimateError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(report.render_json(meta, results, pricer.conv))
    else:
        print()
        print(report.render_text(meta, results, pricer.conv))
        if verbose:
            print(f"\n({pricer.client.search_count} trade searches used.)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
