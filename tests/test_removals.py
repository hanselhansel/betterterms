"""The removed hosts and features stay out of shipped files.

Scans git-tracked files for the removed-name patterns. CHANGELOG.md
and the internal docs set (docs/plans, docs/specs, docs/research,
docs/decisions, TODOS.md; see checks_scan.INTERNAL_DOCS) are exempt:
dated records keep their mentions by design. The removed names are
split into fragments below so this file passes its own scan.
"""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from _lib.checks_scan import is_internal_doc  # noqa: E402

DELETED_PATHS = (
    "GEM" "INI.md",
    "gem" "ini-extension.json",
    "scripts/zip" "-skills",
    "scripts/_lib/gen_" "gem" "ini.py",
    "scripts/_lib/gen_" "cursor" ".py",
    "scripts/_lib/gen_" "mu" "se.py",
    ".cursor" "-plugin",
    ".mu" "se-plugin",
)

PATTERNS = tuple(
    re.compile(pat, re.IGNORECASE)
    for pat in (
        r"gem" r"ini",
        r"cursor" r" rules",
        r"\." r"cursor" r"/",
        r"mu" r"se",
        r"zip" r"-skills",
        r"ju" r"risdiction",
    )
)

EXEMPT = frozenset({Path("CHANGELOG.md")})


def _tracked_files():
    r = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO, capture_output=True, timeout=60,
    )
    if r.returncode != 0:
        raise unittest.SkipTest("not a git checkout")
    return [
        REPO / os.fsdecode(raw) for raw in r.stdout.split(b"\0") if raw
    ]


class RemovedHostsTest(unittest.TestCase):
    def test_removed_hosts_absent(self):
        for rel in DELETED_PATHS:
            with self.subTest(path=rel):
                self.assertFalse((REPO / rel).exists(), rel)
        hits = []
        for path in _tracked_files():
            rel = path.relative_to(REPO)
            if rel in EXEMPT or is_internal_doc(rel):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for pat in PATTERNS:
                if pat.search(text):
                    hits.append(f"{rel}: matches {pat.pattern!r}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
