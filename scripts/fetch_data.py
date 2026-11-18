#!/usr/bin/env python3
"""Download the UCI Online Retail zip and verify its SHA-256.

Usage: python3 scripts/fetch_data.py [out_dir]
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
SHA256 = "f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b"


def main(argv):
    out = Path(argv[1]) if len(argv) > 1 else Path(".tmp")
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL, timeout=120) as resp:
        blob = resp.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != SHA256:
        sys.exit(f"sha256 mismatch: got {digest}, expected {SHA256}")
    target = out / "online_retail.zip"
    target.write_bytes(blob)
    print(f"ok {target} {digest}")


if __name__ == "__main__":
    main(sys.argv)
