#!/usr/bin/env python3
"""Build the UNMINIFIED store-submission zips for the Trade Bridge extension.

One command -> two artifacts in this folder:
  trade-bridge-chrome-edge-<version>.zip   (Chrome Web Store + Edge Add-ons)
  trade-bridge-firefox-<version>.zip       (Firefox AMO)

Source of truth is extension/manifest.json (the clean store manifest: narrowed
host_permissions, placeholder site match, v<version>). This script copies the
extension verbatim (no minification -- reviewers and users can read every line)
and specialises ONLY the manifest per target:

  * Chrome/Edge : manifest.json as-authored. Chrome silently ignores the
                  browser_specific_settings.gecko key, so it is harmless to keep.
  * Firefox     : adds background.scripts (event-page fallback) alongside
                  service_worker for broad Firefox-version compatibility; keeps
                  the required browser_specific_settings.gecko.id.

Excluded from the zips: generate_icons.py, manifest.dev.json (dev-only).

Usage:  python public/dist/build_zips.py
"""
import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))     # buildpricechecker-poe1
EXT = os.path.join(ROOT, "extension")

# Files copied verbatim into every zip (zip-root-relative paths).
PAYLOAD = [
    "background.js",
    "content.js",
    "popup.html",
    "popup.js",
    "README.md",
    "icons/icon16.png",
    "icons/icon32.png",
    "icons/icon48.png",
    "icons/icon128.png",
]


def load_manifest():
    with open(os.path.join(EXT, "manifest.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def chrome_manifest(base):
    """Chrome/Edge: as-authored (service_worker only). Return a copy."""
    m = json.loads(json.dumps(base))
    m["background"] = {"service_worker": "background.js"}
    return m


def firefox_manifest(base):
    """Firefox: add background.scripts fallback; keep gecko id."""
    m = json.loads(json.dumps(base))
    m["background"] = {"service_worker": "background.js", "scripts": ["background.js"]}
    if "browser_specific_settings" not in m or "gecko" not in m.get("browser_specific_settings", {}):
        raise SystemExit("ERROR: Firefox build needs browser_specific_settings.gecko.id in manifest.json")
    return m


def write_zip(out_path, manifest_obj):
    manifest_bytes = (json.dumps(manifest_obj, indent=2) + "\n").encode("utf-8")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", manifest_bytes)
        for rel in PAYLOAD:
            src = os.path.join(EXT, rel.replace("/", os.sep))
            if not os.path.exists(src):
                raise SystemExit("ERROR: missing payload file: " + src)
            z.write(src, rel)
    return out_path


def main():
    base = load_manifest()
    version = base.get("version", "0.0.0")

    # If the content-script domain is still the placeholder, a store would REJECT the zip and it
    # is unsafe to submit. Still build (so the pipeline stays testable) but mark the output name
    # _INVALID_PLACEHOLDER and exit NON-ZERO, so a hurried run can never emit a submittable-looking
    # zip. (Previously this only printed a non-blocking warning.)
    blob = json.dumps(base)
    placeholder = "REPLACE-WITH-YOUR-DOMAIN" in blob
    suffix = "_INVALID_PLACEHOLDER" if placeholder else ""
    if placeholder:
        print("ERROR: manifest.json still has the placeholder content-script match")
        print("       'https://REPLACE-WITH-YOUR-DOMAIN/*'. Replace it with your real public")
        print("       site origin (e.g. https://poe1price.pages.dev/*), then re-run this script.")
        print("       Building CLEARLY-MARKED zips you must NOT submit:\n")

    targets = [
        ("trade-bridge-chrome-edge-%s%s.zip" % (version, suffix), chrome_manifest(base)),
        ("trade-bridge-firefox-%s%s.zip" % (version, suffix), firefox_manifest(base)),
    ]
    for name, mani in targets:
        out = os.path.join(HERE, name)
        write_zip(out, mani)
        size = os.path.getsize(out)
        print("built %s  (%d bytes)" % (name, size))

    if placeholder:
        raise SystemExit("\nREFUSED: placeholder domain present -- outputs marked "
                         "_INVALID_PLACEHOLDER. Fix manifest.json and re-run before submitting.")
    print("\nDone. Unminified store zips are in:\n  " + HERE)


if __name__ == "__main__":
    main()
