"""Differential test: miniyaml.load(text) must either raise
miniyaml.Error or return exactly yaml.safe_load(text). It may never
return a different value. Skipped when PyYAML is not importable."""

import ast
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._lib import frontmatter, miniyaml

try:
    import yaml
except ImportError:
    yaml = None

REPO = Path(__file__).resolve().parents[1]

CORPUS_SKIP_DIRS = {
    ".git", ".claude", "__pycache__", ".venv", "venv", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist",
}

EDGE_CASES = [
    # trailing ':' values
    "k: val:", "k: a:b:", "k: ::", "a: b:\n", "a : : b\n",
    # ': ' inside plain values
    "k: a: b", "k: x:y: z", "k: see: it",
    # '#' comments after values and after block indicators
    "k: v # c", "k: v#notc", 'k: "v" # c', "k: | # c\n  x\n",
    "k: |- # c\n  x\n", "k: >+ # c\n  x\n", "k: |#x\n  a\n",
    # tabs inside block scalars
    "k: |\n  a\tb\n", "k: |\n \ta\n", "k: >\n  \ta\nb: 1\n",
    "k: |\n\ta\n", "k: |\n  a\n\tb\n",
    # first-line-indent vs min-indent block scalars
    "k: |\n    a\n  b\n", "k: |\n  a\n    b\n", "k: |\n   a\n  b\n",
    "k: |\n  a\n   b\n",
    # less-indented continuation lines
    "k: a\n  cont\nj: 1\n", "k: a\n cont\n", "a: b\n c\n", "a:\n  b\n  c\n",
    # multi-line plain scalars
    "a: one\n  two\n", "a:\n  one\n  two\n", "k: a\nb\n",
    # YAML 1.1 ambiguous words
    "k: yes", "k: Yes", "k: YES", "k: no", "k: on", "k: off", "k: ON",
    "k: y", "k: n", "k: tRue", "k: Null", "k: NULL", "k: ~",
    # dates
    "k: 2026-10-03", "k: 2026-1-3", "k: 2026-10-03T10:00:00Z",
    "k: 2026-13-45", "k: 2026-10-03 10:00:00",
    # hex/octal/binary and padded numbers
    "k: 0x1F", "k: -0x1F", "k: 0o17", "k: 007", "k: 08", "k: 0b11",
    "k: 0_1", "k: 9_", "k: 1_000_000", "k: 0x", "k: 0b", "k: 0", "k: 00",
    "k: -0", "k: 1_0", "k: 1:30", "k: 1:60", "k: 1:5", "k: 12:34:56",
    "k: -1:30", "k: .inf", "k: -.inf", "k: +.inf", "k: .NaN", "k: +.nan",
    "k: .infx", "k: -.infx",
    # empty values
    "k:", "k: ", "k: \n\n- notseq\n", "- ", "-\n", "- a\n- b\n",
    # unicode line separators
    'k: "a\\u2028b"', "a: 1\u2028b: 2", "k: a\u2029b", "a: 1\x85b: 2",
    'k: "a\x85b"',
    # CRLF and lone CR
    "a: 1\r\nb: 2\r\n", "a: 1\rb: 2", 'k: "a\rb"', "a: x\ry\n",
    # BOM
    "\ufeffa: 1", "a: \ufeffx", 'k: "\ufeffx"', "\ufeff\ufeffa: 1",
    # nested '- |' under list items
    "- |\n  a\n- b\n", "k:\n  - |\n    x\n  - y\n", "- |\n  a\n  b\n- c\n",
    "- |\nx\n", "- k: |\n  x\n", "- |\n  a\n\n- b\n",
    # lone block scalar indicator on a deeper line
    "a:\n  |\n    x\nb: 2\n", "a:\n  >-\n    x\n", "-\n  |\n    x\n",
    "|\n  a\n", "k:\n  |\n    x\n    y\n  - z\n",
    # duplicate keys
    "a: 1\na: 2\n", "a: 1\nb: 2\na: 3\n",
    # document markers
    "--- x", "---\na: 1\n---\n", "...\n", "a: 1\n...\n", "  ---\n",
    "k: ---", "- ---\n- x\n", "x\n---\n", "---\n---\na: 1\n",
    "a:\n  ---\n", "... x", "---x", "k: ...",
    # indicators and tags
    "k: - x", "k: ? x", "k: : x", "k: ,x", "k: ]x", "k: }x", "k: -",
    "k: ?", "k: :", "k: =", "k: <<", "? k: v", "<<: {a: 1}",
    "k: -x", "k: ?x", "k: :x", "k: ::x", "k: *x", "k: &a x\nj: *a",
    "k: !t v", "k: !!str x", "k: |2\n  a\n",
    # flow collections
    "k: [a,]", "k: [,]", "k: {a:}", "k: [a:]", "{<<: 1}", "{<<: {a: 1}}",
    "k: {a:b}", "k: [a: b]", "k: {a: 1,}", "a: [1,\n  2]",
    "k: [a,{b: 2},[c]]", "k: [a b]", "k: [1, 2", "k: {a: 1",
    "{a: b: c}", "k: a,b", "k: a]", "k: a}",
    # scalars and resolution
    "k: 1e5", "k: 1e+5", "k: 1.e5", "k: 1.5e3", "k: 1.5e+3", "k: -.5",
    "k: +.5", "k: .5", "k: 1.", "k: -1", "k: +1", "k: -1.5", "k: .5e+1",
    "k: 0.5e2", "k: 12.3e-4", "k: 1.2.3", "k: 123abc", "k: .",
    # quoted scalars and escapes
    'k: "a\\_b"', 'k: "a\\Nb"', 'k: "a\\Lb"', 'k: "a\\Pb"', 'k: "a\\0b"',
    'k: "a\\eb"', 'k: "a\\tb"', 'k: "a\\\\b"', 'k: "a\\/b"', 'k: "a\\ b"',
    'k: "\\x4g"', 'k: "\\u1234"', 'k: "\\x41"', 'k: "\\U00000041"',
    "k: 'it''s'", 'k: "a" b', 'k: "a" "b"', 'k: "a\n b"', 'k: "a\tb"',
    "k: 'a\\tb'", 'k: "multi\nline"',
    # structure and nesting
    "a:\n- - x\n", "k:\n- a\n  b\n", "k:\n- a\n  b\n",
    "- a: 1\n  b: 2\n", "k: v\n  w: x\n", "k: v\n\tj: 2\n",
    "\ta: 1\n", "a:\t1\n", "k: a\tb\n", "k: v\n\t\n",
    "a\nb: 1\n", "x\n---\n", "k:\n    x: 1\n", "k: v  \n",
    'k: "x"  \n', "a:b: c", ":: k", "a :b", "a:b c", "k:1",
    "k: #c", "k: a#b",
]


def repo_corpus():
    """Every *.yaml file and SKILL.md frontmatter block in the repo."""
    texts = []
    for path in sorted(REPO.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO)
        if any(part in CORPUS_SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix in (".yaml", ".yml"):
            texts.append(path.read_text(encoding="utf-8"))
        elif path.name == "SKILL.md":
            block = frontmatter.block(path)
            if block is not None:
                texts.append(block)
    return texts


def test_file_strings():
    """Every string literal in the miniyaml and frontmatter test files."""
    texts = []
    for name in ("test_miniyaml.py", "test_frontmatter.py"):
        tree = ast.parse((REPO / "tests" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                texts.append(node.value)
            elif isinstance(node, ast.JoinedStr):
                texts.extend(
                    v.value
                    for v in node.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
    return texts


@unittest.skipUnless(yaml is not None, "PyYAML required for differential tests")
class DifferentialTest(unittest.TestCase):
    def assert_consistent(self, text):
        try:
            mine = miniyaml.load(text)
        except miniyaml.Error:
            return
        except Exception as e:
            self.fail(f"{e!r} (not miniyaml.Error) for {text!r}")
        try:
            want = yaml.safe_load(text)
        except Exception:
            self.fail(f"miniyaml returned {mine!r} where PyYAML raises: {text!r}")
        self.assertEqual(mine, want, f"for {text!r}")

    def test_repo_yaml_corpus(self):
        for text in repo_corpus():
            with self.subTest(text=text[:80]):
                self.assert_consistent(text)

    def test_test_file_strings(self):
        for text in test_file_strings():
            with self.subTest(text=text[:80]):
                self.assert_consistent(text)

    def test_edge_cases(self):
        self.assertGreaterEqual(len(EDGE_CASES), 60)
        for text in EDGE_CASES:
            with self.subTest(text=text[:80]):
                self.assert_consistent(text)


@unittest.skipUnless(yaml is not None, "PyYAML required for differential tests")
class DumpRoundTripTest(unittest.TestCase):
    STR_POOL = [
        "", "x", "yes", "no", "On", "off", "y", "n", "true", "007", "0x1F",
        "1.5", "1e5", "2026-10-03", "2026-10-03T10:00:00Z", "a: b", "a:b",
        "#c", "x # y", "- x", "-x", "|", ">", "-", "~", "null", "Null",
        "café", "a\tb", "a\nb", "trailing ", " lead", "it's", 'a "b" c',
        "a; b", "[a]", "{k}", "a, b", "x:", ":", "1:30", "0o17", ".5",
        ".inf", "12:34:56", "*a", "&a", "!t", "@r", "`z`", "%p", "a\x07b",
        "line\u2028sep", "a\x85b", "\ufeffx", "...", "---", "--", "=",
        "<<", "12.5e+3", "-1", "+3", ".5e+2", "1_000", "0b101", "9_",
        "0.5e-3", "-.5", "2026-1-3", "see: it", "val:",
    ]

    def test_dump_round_trips_through_pyyaml(self):
        rng = random.Random(20261003)
        pool = self.STR_POOL

        def gen(depth):
            r = rng.random()
            if depth > 2 or r < 0.5:
                kind = rng.choice("sifbn")
                if kind == "s":
                    return rng.choice(pool)
                if kind == "i":
                    return rng.randint(-(10**12), 10**12)
                if kind == "f":
                    return rng.choice([0.0, -1.5, 2.25, 1e20, -3.5e-10, 1.0, 0.001])
                if kind == "b":
                    return rng.random() < 0.5
                return None
            if r < 0.75:
                return [gen(depth + 1) for _ in range(rng.randint(0, 4))]
            return {
                rng.choice(pool) or "k": gen(depth + 1)
                for _ in range(rng.randint(0, 4))
            }

        for _ in range(200):
            obj = gen(0)
            dumped = miniyaml.dump(obj)
            self.assertEqual(yaml.safe_load(dumped), obj, dumped)
            self.assertEqual(miniyaml.load(dumped), obj, dumped)


if __name__ == "__main__":
    unittest.main()
