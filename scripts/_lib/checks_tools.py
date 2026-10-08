"""Checks that shell out: unit tests, vendor sync, build, version, and
host-tool validators."""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .checks_scan import (
    SUBPROCESS_TIMEOUT,
    display,
    join,
    junk_file,
    tail,
)

UNIT_TEST_TIMEOUT = 900


def check_unit_tests(root):
    if not (root / "tests").is_dir():
        return "SKIP", "no tests/ directory"
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=root, capture_output=True, text=True, timeout=UNIT_TEST_TIMEOUT,
    )
    if r.returncode != 0:
        return "FAIL", tail(r)
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
    return ("PASS", "") if r.returncode == 0 else ("FAIL", tail(r))


def _payload(p, linked):
    """{relpath: bytes} under a dir, a file's own bytes keyed "", or {}
    when the path does not exist. The rule is the same whether the file
    list came from git or os.walk: every file on disk counts except
    __pycache__ contents and OS cruft. A symlinked directory anywhere in
    the tree is appended to linked instead of followed."""
    if p.is_symlink() and p.is_dir():
        linked.append(str(p))
        return {}
    if p.is_file():
        return {"": p.read_bytes()}
    out = {}
    if p.is_dir():
        for dirpath, dirnames, filenames in os.walk(p):
            kept = []
            for d in dirnames:
                if (Path(dirpath) / d).is_symlink():
                    linked.append(str(Path(dirpath) / d))
                elif d != "__pycache__":
                    kept.append(d)
            dirnames[:] = kept
            for name in filenames:
                if not junk_file(name):
                    f = Path(dirpath) / name
                    out[str(f.relative_to(p))] = f.read_bytes()
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
    skills/betterterms-guardrails/scripts/btlib is absent. Symlinked
    directories FAIL: the walk cannot follow them, so their contents
    could drift invisibly."""
    btlib = root / "skills/betterterms-guardrails/scripts/btlib"
    if not btlib.is_dir():
        return "SKIP", "no skills/betterterms-guardrails/scripts/btlib"
    problems = []
    linked = []
    for rel, src in (("_vendor/yaml", "_vendor/yaml"), ("yaml.py", "miniyaml.py")):
        mine = _payload(btlib / rel, linked)
        theirs = _payload(root / "scripts/_lib" / src, linked)
        if mine != theirs:
            problems.append(
                f"btlib/{rel} is not identical to scripts/_lib/{src}"
                f" (first diff: {display(_first_diff(rel, mine, theirs))})"
            )
    problems += [
        f"{display(Path(d).relative_to(root))}: symlinked directory"
        for d in linked
    ]
    return ("FAIL", join(problems)) if problems else ("PASS", "")


def check_build_fresh(root):
    return _run_script(root, "build", "--check")


def check_version_sync(root):
    return _run_script(root, "bump-version", "--check")


def check_eval_smoke(root):
    if not (root / "evals").is_dir():
        return "SKIP", "no evals/ directory"
    return _run_script(root, "eval", "--smoke")


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
    return ("PASS", "") if r.returncode == 0 else ("FAIL", tail(r))


def check_claude_validate(root):
    return _validate(root, ".claude-plugin/plugin.json", "claude",
                     ["plugin", "validate", "."], "no .claude-plugin/plugin.json")


def _pty(argv):
    """The command wrapped in a pseudo-terminal through script(1) when
    this check's stdout is not a terminal: the mod's validate and test
    subcommands misbehave without one. BSD script (macOS) takes the
    command after the file; util-linux script takes ``-c``. When
    script(1) is absent the command runs as is."""
    if sys.stdout.isatty() or shutil.which("script") is None:
        return argv
    if sys.platform == "darwin":
        return ["script", "-q", "/dev/null", *argv]
    return [
        "script", "-qec",
        " ".join(shlex.quote(a) for a in argv), "/dev/null",
    ]


def check_mod_tests(root):
    """The mod's node --test suite. ``node --test <dir>`` treats the
    directory itself as one test file on Node 24, so the suite runs
    with the mod directory as cwd instead."""
    if not (root / "mod").is_dir():
        return "SKIP", "no mod/ directory"
    if shutil.which("node") is None:
        return "SKIP", "node not installed"
    r = subprocess.run(
        ["node", "--test"], cwd=root / "mod",
        capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
    )
    return ("PASS", "") if r.returncode == 0 else ("FAIL", tail(r))


def check_mod_validate(root):
    """`claude plugin validate --strict mod` and `claude plugin test
    mod`. Without the claude binary this is a SKIP, never a PASS."""
    if not (root / "mod" / ".claude-plugin" / "plugin.json").is_file():
        return "SKIP", "no mod/.claude-plugin/plugin.json"
    if shutil.which("claude") is None:
        return "SKIP", "claude not installed"
    for args in (
        ["plugin", "validate", "--strict", "mod"],
        ["plugin", "test", "mod"],
    ):
        r = subprocess.run(
            _pty(["claude", *args]),
            cwd=root, capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        if r.returncode != 0:
            return "FAIL", tail(r)
    return "PASS", ""
