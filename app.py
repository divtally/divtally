#!/usr/bin/env python
"""Entry point for the packaged (one-file .exe) build.

Double-clicking the .exe runs this: it starts the local web server and opens the
browser automatically. Kept deliberately bullet-proof so a non-technical user always
sees a friendly message (and the window stays open on any error)."""
import sys
import traceback


def _pause(msg=""):
    try:
        input((msg + "\n\n" if msg else "") + "Press Enter to close this window...")
    except Exception:
        pass


def main():
    print("=" * 56)
    print("   PoE2 Build Price Checker")
    print("=" * 56)
    print("   Your web browser should open in a few seconds.")
    print("   If it doesn't, open this address yourself:")
    print("")
    print("        http://127.0.0.1:8765")
    print("")
    print("   >> KEEP THIS BLACK WINDOW OPEN while you use it. <<")
    print("   Close this window when you are finished.")
    print("=" * 56)
    print("")
    try:
        from bpc.web import main as serve
        serve([])                      # opens the browser, serves until closed
    except SystemExit as e:
        _pause(str(e) or "The app could not start (the port may be in use).")
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        _pause("Sorry - something went wrong starting the app.")


if __name__ == "__main__":
    main()
