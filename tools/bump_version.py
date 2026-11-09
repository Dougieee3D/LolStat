"""Set LoLStat's version everywhere at once, and refresh CHANGELOG.md.

    python tools/bump_version.py 4.0.2

Write the patch notes for the new version in patch_notes.py first (this refuses to run without them).
Then commit and push to main: GitHub builds, scans and publishes LoLStat-Setup.exe as release v<version>.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import patch_notes  # noqa: E402


def sub(path, pattern, repl, count=1):
    p = os.path.join(ROOT, path)
    s = open(p, encoding="utf-8").read()
    s2, n = re.subn(pattern, repl, s, count=count)
    if n != count:
        sys.exit(f"Couldn't find the version in {path}")
    open(p, "w", encoding="utf-8", newline="").write(s2)


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("usage: python tools/bump_version.py X.Y.Z")
    v = sys.argv[1]
    if patch_notes.latest()["version"] != v:
        sys.exit(f"Add the patch notes for {v} at the top of patch_notes.py first")
    a, b, c = (int(x) for x in v.split("."))
    sub("lolstat_assets.py", r'APP_VERSION = "[^"]+"', f'APP_VERSION = "{v}"')
    sub("installer.iss", r'#define MyAppVersion "[^"]+"', f'#define MyAppVersion "{v}"')
    sub("version_info.txt", r"filevers=\(\d+, \d+, \d+, \d+\)", f"filevers=({a}, {b}, {c}, 0)")
    sub("version_info.txt", r"prodvers=\(\d+, \d+, \d+, \d+\)", f"prodvers=({a}, {b}, {c}, 0)")
    sub("version_info.txt", r"'FileVersion', '[\d.]+'", f"'FileVersion', '{v}.0'")
    sub("version_info.txt", r"'ProductVersion', '[\d.]+'", f"'ProductVersion', '{v}.0'")
    open(os.path.join(ROOT, "CHANGELOG.md"), "w", encoding="utf-8").write(patch_notes.changelog())
    print(f"LoLStat is now {v}. Commit and push to main to release it.")


if __name__ == "__main__":
    main()
