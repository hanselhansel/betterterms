"""Checks that shell out: unit tests, vendor sync, build, version, and
host-tool validators."""

import shutil
import subprocess
import sys

from .checks_scan import (
    SUBPROCESS_TIMEOUT,
    _file_list,
    _join,
    _junk_file,
    _tail,
)

UNIT_TEST_TIMEOUT = 300


def check_unit_tests(root):
    if not (root / "tests").is_dir():
        return "SKIP", "no tests/ directory"
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=root, capture_output=True, text=True, timeout=UNIT_TEST_TIMEOUT,
    )
    if r.returncode != 0:
        return "FAIL", _tail(r)
    if "Ran 0 tests" in (r.stderr or "") + (r.stdout or ""):
        return "FAIL", "test run discovered 0 tests"
    return "PASS", ""


def _run_script(root, name, *args):
    path = root / "scripts" / name
    if not path.is_file():
        return "SKIP", f"no scripts/{name}"
    r = subprocess.run(
        [sys.executable, str(path), *args], cwd=root,
        capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
    )
    return ("PASS", "") if r.returncode == 0 else ("FAIL", _tail(r))


def _payload(p, listed):
    """{relpath: bytes} under a dir, a file's own bytes keyed "", or {}
    when the path does not exist. Only files in the verify file list
    count; __pycache__, .DS_Store and editor swap files never do."""
    if p.is_file():
        return {"": p.read_bytes()}
    out = {}
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            rel = f.relative_to(p)
            if (
                not f.is_file()
                or "__pycache__" in rel.parts
                or _junk_file(f.name)
                or f not in listed
            ):
                continue
            out[str(rel)] = f.read_bytes()
    return out


def _first_diff(rel, a, b):
    """The first path inside rel whose bytes differ or exist on one side
    only, prefixed by rel."""
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            return f"{rel}/{key}" if key else rel
    return rel


def check_vendor_sync(root):
    """btlib ships byte-identical copies of the YAML layer; SKIP when
    skills/betterterms-guardrails/scripts/btlib is absent."""
    btlib = root / "skills/betterterms-guardrails/scripts/btlib"
    if not btlib.is_dir():
        return "SKIP", "no skills/betterterms-guardrails/scripts/btlib"
    listed = set(_file_list(root))
    problems = []
    for rel, src in (("_vendor/yaml", "_vendor/yaml"), ("yaml.py", "miniyaml.py")):
        mine = _payload(btlib / rel, listed)
        theirs = _payload(root / "scripts/_lib" / src, listed)
        if mine != theirs:
            problems.append(
                f"btlib/{rel} is not identical to scripts/_lib/{src}"
                f" (first diff: {_first_diff(rel, mine, theirs)})"
            )
    return ("FAIL", _join(problems)) if problems else ("PASS", "")


def check_build_fresh(root):
    return _run_script(root, "build", "--check")


def check_version_sync(root):
    return _run_script(root, "bump-version", "--check")


def _validate(root, marker, tool, args, skip_msg):
    """Run a host tool's validator when its manifest and binary exist."""
    if not (root / marker).is_file():
        return "SKIP", skip_msg
    if shutil.which(tool) is None:
        return "SKIP", f"{tool} not installed"
    r = subprocess.run(
        [tool, *args],
        cwd=root, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
    )
    return ("PASS", "") if r.returncode == 0 else ("FAIL", _tail(r))


def check_claude_validate(root):
    return _validate(root, ".claude-plugin/plugin.json", "claude",
                     ["plugin", "validate", "."], "no .claude-plugin/plugin.json")


def check_gemini_validate(root):
    return _validate(root, "gemini-extension.json", "gemini",
                     ["extensions", "validate", "."], "no gemini-extension.json")
