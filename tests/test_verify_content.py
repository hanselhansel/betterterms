"""Content-scanning verify checks: local-path patterns, UTF-8 decoding,
vendor roots, evals holdout and vendor-sync drift."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from test_verify import (
    FILE_URI_HOME,
    MAC_HOME,
    UNIX_HOME,
    WIN_HOME_FWD,
    VerifyRepoCase,
    make_repo_root,
    run_verify,
)


class VerifyContentTest(VerifyRepoCase):
    def test_file_uri_eol_home_and_forward_slash_windows_fail(self):
        (self.root / "f.txt").write_text(f"see {FILE_URI_HOME}\n")
        (self.root / "h.txt").write_text(f"home is {UNIX_HOME[:-5]}")
        (self.root / "w.txt").write_text(f"see {WIN_HOME_FWD}\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("f.txt:1", proc.stdout)
        self.assertIn("h.txt:1", proc.stdout)
        self.assertIn("w.txt:1", proc.stdout)

    def test_local_paths_in_decoded_json_and_yaml_values_fail(self):
        # Raw text keeps escapes; only the decoded value shows the path.
        (self.root / "c.json").write_text('{"p": "C:\\\\Users\\\\alice\\\\repo"}\n')
        (self.root / "d.yaml").write_text('p: "C:\\\\Users\\\\bob"\n')
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("c.json: string value", proc.stdout)
        self.assertIn("d.yaml: string value", proc.stdout)

    def test_mount_flag_equals_and_root_paths_fail(self):
        root_home = "/" + "root/app/out.log"  # built so this file passes
        (self.root / "m.txt").write_text("docker run -v" + MAC_HOME + ":/x img\n")
        (self.root / "e.txt").write_text("HOME=" + MAC_HOME + "\n")
        (self.root / "r.txt").write_text("log: " + root_home + "\n")
        (self.root / "w.txt").write_text("see " + UNIX_HOME[:-5] + " notes\n")
        # Extended by /ship coverage audit.
        # Value: protects=a tilde home path to a named dir fails while
        # ~/.dotfiles pass; fails_when=the ~/ alternative in LOCAL_PATH is
        # dropped; why_new=only the passing ~/.claude case was tested; seam=none
        (self.root / "t.txt").write_text("clone into ~" + "/projects/x\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        for rel in ("m.txt:1", "e.txt:1", "r.txt:1", "w.txt:1", "t.txt:1"):
            self.assertIn(rel, proc.stdout)

    @unittest.skipIf(
        os.name == "nt" or os.geteuid() == 0, "needs a non-root POSIX user"
    )
    def test_unreadable_file_fails_naming_path(self):
        p = self.root / "locked.txt"
        p.write_text("x\n")
        p.chmod(0)
        self.addCleanup(p.chmod, 0o644)
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("locked.txt: cannot read", proc.stdout)

    def test_non_utf8_text_file_fails_but_binary_skipped(self):
        (self.root / "img.bin").write_bytes(b"\x89PNG\x00\x0d\x0a\x1a\x0a")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL", proc.stdout)
        (self.root / "latin.txt").write_bytes(b"caf\xe9\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("latin.txt: not valid UTF-8", proc.stdout)

    def test_non_utf8_md_and_py_fail_prose_rules_and_file_size(self):
        (self.root / "doc.md").write_bytes(b"text \xe9\n")
        (self.root / "code.py").write_bytes(b"x = '\xe9'\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertIn("doc.md: not valid UTF-8", proc.stdout)
        self.assert_failed(proc, "file-size")
        self.assertIn("code.py: not valid UTF-8", proc.stdout)

    def test_unit_tests_fails_when_zero_tests_run(self):
        (self.root / "tests").mkdir()
        proc = run_verify(self.root)
        self.assert_failed(proc, "unit-tests")
        self.assertIn("0 tests", proc.stdout)

    def test_skill_name_rejects_bad_hyphens_and_long_names(self):
        for folder in (
            "betterterms-x-",
            "betterterms-x--y",
            "betterterms--x",
            "betterterms-" + "x" * 53,
        ):
            with self.subTest(folder=folder):
                with tempfile.TemporaryDirectory() as tmp:
                    self.root = Path(tmp)
                    make_repo_root(self.root)
                    self.add_skill(folder=folder, name=folder)
                    self.assert_failed(run_verify(self.root), "skill-names")

    def test_vendor_exemption_applies_only_to_known_roots(self):
        other = self.root / "other" / "_vendor"
        other.mkdir(parents=True)
        (other / "notes.md").write_text(f"built under {MAC_HOME} \u2014 delving\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("other/_vendor/notes.md:1", proc.stdout)
        self.assert_failed(proc, "prose-rules")

    def test_evals_holdout_skipped_but_evals_scanned(self):
        holdout = self.root / "evals" / "holdout"
        holdout.mkdir(parents=True)
        (holdout / "cases.md").write_text("em \u2014 dash\n")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL prose-rules", proc.stdout)
        (self.root / "evals" / "scored.md").write_text("em \u2014 dash\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertNotIn("holdout", proc.stdout)

    def test_nul_or_utf_bom_in_text_named_file_fails(self):
        (self.root / "nul.md").write_bytes(b"a\x00b\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("nul.md", proc.stdout)
        # A UTF-16 or UTF-32 BOM counts too, on a text suffix or on an
        # extensionless scripts/ entry point.
        (self.root / "nul.md").unlink()
        (self.root / "bom.yaml").write_bytes(b"\xff\xfea\x00:\x00 \x001\x00\n\x00")
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "tool").write_bytes(b"\xfe\xff\x00x\x00=\x001\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("bom.yaml", proc.stdout)
        self.assertIn("scripts/tool", proc.stdout)
        # Binary files under non-text names still skip silently.
        (self.root / "bom.yaml").unlink()
        (self.root / "scripts" / "tool").unlink()
        (self.root / "raw.bin").write_bytes(b"\x00\x01\x02")
        proc = run_verify(self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # But a UTF-16/32 BOM FAILs as not UTF-8 under ANY suffix: such
        # content can never be valid UTF-8.
        (self.root / "blob.bin").write_bytes(b"\xff\xfe\x00\x00rest")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("blob.bin: not valid UTF-8", proc.stdout)

    def test_vendor_sync_ignores_junk_and_names_first_drift(self):
        # A NON-empty vendored tree: two small files mirrored both ways.
        btlib = self.root / "skills/betterterms-guardrails/scripts/btlib"
        canon = self.root / "scripts/_lib"
        for base in (btlib / "_vendor" / "yaml", canon / "_vendor" / "yaml"):
            base.mkdir(parents=True)
            (base / "a.py").write_text("A\n")
            (base / "b.py").write_text("B\n")
        (btlib / "yaml.py").write_text("same\n")
        (canon / "miniyaml.py").write_text("same\n")
        # OS cruft, editor swap files and __pycache__ do not count as drift.
        (btlib / "_vendor" / "yaml" / ".DS_Store").write_bytes(b"junk\x00")
        (canon / "_vendor" / "yaml" / "a.py.swp").write_text("swap\n")
        (canon / "_vendor" / "yaml" / "c.py~").write_text("backup\n")
        pycache = btlib / "_vendor" / "yaml" / "__pycache__"
        pycache.mkdir()
        (pycache / "a.cpython-311.pyc").write_bytes(b"\x00compiled")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL vendor-sync", proc.stdout)
        (btlib / "_vendor" / "yaml" / "b.py").write_text("drifted\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "vendor-sync")
        self.assertIn("b.py", proc.stdout)

    @unittest.skipIf(os.name == "nt", "needs POSIX symlinks")
    def test_vendor_sync_fails_on_symlinked_directory(self):
        # A symlinked dir is never followed (its contents could drift
        # invisibly); it FAILs the check by name instead.
        btlib = self.root / "skills/betterterms-guardrails/scripts/btlib"
        canon = self.root / "scripts/_lib"
        for base in (btlib / "_vendor" / "yaml", canon / "_vendor" / "yaml"):
            base.mkdir(parents=True)
            (base / "a.py").write_text("A\n")
        (btlib / "yaml.py").write_text("same\n")
        (canon / "miniyaml.py").write_text("same\n")
        target = canon / "_vendor" / "yaml"
        (btlib / "_vendor" / "yaml" / "linked").symlink_to(target)
        proc = run_verify(self.root)
        self.assert_failed(proc, "vendor-sync")
        self.assertIn("symlinked directory", proc.stdout)
        self.assertIn("linked", proc.stdout)
        # Extended by /ship coverage audit.
        # Value: protects=btlib/_vendor/yaml itself symlinked to the canonical
        # tree FAILs, though its bytes compare equal; fails_when=_payload's
        # top-level symlink guard is removed and os.walk follows the link;
        # why_new=only a nested symlink was tested; seam=none
        (btlib / "_vendor" / "yaml" / "linked").unlink()
        shutil.rmtree(btlib / "_vendor" / "yaml")
        (btlib / "_vendor" / "yaml").symlink_to(target)
        proc = run_verify(self.root)
        self.assert_failed(proc, "vendor-sync")
        self.assertIn("_vendor/yaml: symlinked directory", proc.stdout)

    def test_em_dash_entities_in_shipped_markdown_fail(self):
        for ent in ("&mdash;", "&#8212;"):
            with self.subTest(entity=ent):
                self.add_skill(extra_body=f"offer one {ent} offer two\n")
                proc = run_verify(self.root)
                self.assert_failed(proc, "prose-rules")
                self.assertIn("em dash", proc.stdout)

    def test_text_suffixes_cover_every_scanned_suffix(self):
        # .sh and .ts are text names: NUL bytes inside them FAIL as
        # binary-in-text instead of being skipped like real binaries.
        (self.root / "s.sh").write_bytes(b"echo \x00\n")
        (self.root / "t.ts").write_bytes(b"let x\x00\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("s.sh: binary content in a text file", proc.stdout)
        self.assertIn("t.ts: binary content in a text file", proc.stdout)

    def test_home_name_ending_at_colon_fails(self):
        # /home/<name> counts when ':' follows the name too, on any
        # left edge (mount specs, PATH entries), not only after '-v'.
        (self.root / "m.txt").write_text("mnt=" + "/" + "home/a:/z\n")
        (self.root / "p.txt").write_text("PATH=/bin:" + "/" + "home/u:/sbin\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("m.txt:1", proc.stdout)
        self.assertIn("p.txt:1", proc.stdout)

    @unittest.skipIf(os.name == "nt", "needs POSIX symlinks")
    def test_walk_mode_symlinks_fail_no_symlinks(self):
        # With no .git the walk reports file links and dir links alike,
        # never following the dir link into its contents.
        real = self.root / "real"
        real.mkdir()
        (real / "f.txt").write_text("x\n")
        (self.root / "file-link").symlink_to("VERSION")
        (self.root / "dir-link").symlink_to(
            "real", target_is_directory=True
        )
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-symlinks")
        self.assertIn("file-link", proc.stdout)
        self.assertIn("dir-link", proc.stdout)
        self.assertIn("PASS no-local-paths", proc.stdout)

    def test_colon_left_edge_flags_home_paths_except_url_schemes(self):
        # ':' counts as a left edge (PATH entries, host:container
        # mounts) unless it ends an http:, https: or file: scheme.
        (self.root / "p.txt").write_text("PATH=/bin:" + UNIX_HOME + "\n")
        (self.root / "c.txt").write_text(
            "docker -v /img:" + "/" + "root/app\n"
        )
        (self.root / "s.txt").write_text("PATH=$PATH:" + MAC_HOME + "/bin\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        for rel in ("p.txt:1", "c.txt:1", "s.txt:1"):
            self.assertIn(rel, proc.stdout)
        for rel in ("p.txt", "c.txt", "s.txt"):
            (self.root / rel).unlink()
        (self.root / "u.txt").write_text(
            "see http:/"
            + "home/x then https:/"
            + "Users/x and file:/"
            + "root/x\n"
        )
        proc = run_verify(self.root)
        self.assertNotIn("FAIL no-local-paths", proc.stdout)

    def test_dash_v_and_file_uri_edges_for_unix_homes(self):
        # /home and /root take the same left edges as /Users: '-v'
        # mounts, '=' and file:/// URIs all count.
        (self.root / "v.txt").write_text(
            "docker run -v"
            + "/"
            + "home/u/data -v"
            + "/"
            + "root/d -v"
            + "/"
            + "home/v:/z img\n"
        )
        (self.root / "e.txt").write_text("ROOTFS=" + "/" + "root/app\n")
        (self.root / "f.txt").write_text(
            "uri " + "file://" + "/" + "root/app\n"
        )
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        for rel in ("v.txt:1", "e.txt:1", "f.txt:1"):
            self.assertIn(rel, proc.stdout)

    def test_skill_md_must_be_exact_case(self):
        # 'skill.md' does not satisfy the SKILL.md requirement, even on
        # case-insensitive filesystems where is_file() would find it.
        d = self.root / "skills" / "betterterms-x"
        d.mkdir(parents=True)
        (d / "skill.md").write_text(
            "---\nname: betterterms-x\ndescription: Does a thing.\n---\nbody\n"
        )
        proc = run_verify(self.root)
        self.assert_failed(proc, "skill-names")
        self.assertIn("missing SKILL.md", proc.stdout)

    def test_optional_frontmatter_field_types(self):
        # Valid optional fields pass.
        self.write_skill(
            "---\n"
            "name: betterterms-x\n"
            "description: Does a thing.\n"
            "license: MIT\n"
            "compatibility: needs git\n"
            "metadata:\n  author: someone\n  version: '1'\n"
            "allowed-tools: [Read, Bash]\n"
            "---\nbody\n"
        )
        proc = run_verify(self.root)
        self.assertNotIn("FAIL skill-names", proc.stdout)
        # And the string form of allowed-tools is fine too.
        self.write_skill(
            "---\nname: betterterms-x\ndescription: Does a thing.\n"
            "allowed-tools: Read\n---\nbody\n"
        )
        self.assertNotIn("FAIL skill-names", run_verify(self.root).stdout)

        cases = [
            ("license: 2026\n", "license must be a string"),
            ("compatibility: 5\n", "compatibility must be a string"),
            ("compatibility: " + "x" * 501 + "\n", "<= 500 chars"),
            ("metadata: [a, b]\n", "metadata must map strings to strings"),
            ("metadata:\n  author: 7\n", "metadata must map strings to strings"),
            ("allowed-tools: [Read, 7]\n", "allowed-tools must be a string or list"),
            ("allowed-tools:\n  x: y\n", "allowed-tools must be a string or list"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra):
                self.write_skill(
                    "---\nname: betterterms-x\ndescription: Does a thing.\n"
                    + extra
                    + "---\nbody\n"
                )
                proc = run_verify(self.root)
                self.assert_failed(proc, "skill-names")
                self.assertIn(message, proc.stdout)


if __name__ == "__main__":
    unittest.main()
