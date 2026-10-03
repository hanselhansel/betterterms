import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERSION = (REPO / "VERSION").read_text(encoding="utf-8").strip()

SKILL_NAMES = sorted(
    p.name for p in (REPO / "skills").iterdir()
    if p.is_dir() and p.name.startswith("betterterms-")
)


def make_repo(tmp):
    """A throwaway repo copy: scripts, skills, hooks and the two root
    config files, so script tests never touch the real tree."""
    root = Path(tmp) / "repo"
    root.mkdir()
    for d in ("scripts", "skills", "hooks"):
        shutil.copytree(
            REPO / d, root / d,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for name in ("VERSION", "kit.config.json"):
        shutil.copy2(REPO / name, root / name)
    return root


def write_skill(parent, name):
    d = Path(parent) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n\nBody.\n"
    )
    return d


def run(root, name, *args, home=None, extra_env=None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
    env.pop("BETTERTERMS_HOME", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(root / "scripts" / name), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


class ScriptTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = make_repo(self.tmp)
        self.home = self.tmp / "home"
        (self.home / ".agents" / "skills").mkdir(parents=True)
        (self.home / ".claude" / "skills").mkdir(parents=True)


class InstallSkillsTest(ScriptTestCase):
    def install(self, *args):
        return run(self.repo, "install-skills", *args, home=self.home)

    def test_links_every_skill(self):
        target = self.tmp / "target"
        proc = self.install("--target", str(target))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in SKILL_NAMES:
            link = target / name
            self.assertTrue(link.is_symlink(), name)
            self.assertEqual(
                link.resolve(), (self.repo / "skills" / name).resolve()
            )

    def test_links_are_idempotent(self):
        target = self.tmp / "target"
        for _ in range(2):
            proc = self.install("--target", str(target))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((target / "betterterms-start").is_symlink())

    def test_refuses_when_skill_in_both_shared_dirs(self):
        for base in (".agents/skills", ".claude/skills"):
            write_skill(self.home / base, "betterterms-start")
        target = self.tmp / "target"
        proc = self.install("--target", str(target))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("betterterms-start", proc.stderr + proc.stdout)
        self.assertFalse((target / "betterterms-start").exists())

    def test_refuses_to_create_a_duplicate(self):
        write_skill(self.home / ".claude" / "skills", "betterterms-start")
        target = self.home / ".agents" / "skills"
        proc = self.install("--target", str(target))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse((target / "betterterms-start").exists())

    def test_copy_installs_real_dirs_and_version_marker(self):
        target = self.tmp / "target"
        proc = self.install("--target", str(target), "--copy")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        skill = target / "betterterms-start"
        self.assertTrue(skill.is_dir())
        self.assertFalse(skill.is_symlink())
        self.assertTrue((skill / "SKILL.md").is_file())
        marker = target / ".betterterms-version"
        self.assertEqual(marker.read_text().strip(), VERSION)

    def test_refuses_symlinks_inside_the_repo(self):
        target = self.repo / ".claude" / "skills"
        proc = self.install("--target", str(target))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse((target / "betterterms-start").exists())
        proc = self.install("--target", str(target), "--copy")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((target / "betterterms-start").is_dir())

    def test_usage_errors_exit_2(self):
        for args in ([], ["--copy"], ["--bogus"],
                     ["--target"], ["--target", "x", "y"]):
            with self.subTest(args=args):
                proc = self.install(*args)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)


class VendorIntoRepoTest(ScriptTestCase):
    def test_vendors_skills_and_writes_version_marker(self):
        target = self.tmp / "consumer"
        (target / ".git").mkdir(parents=True)
        proc = run(self.repo, "vendor-into-repo", str(target), home=self.home)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        bt = target / ".claude/skills/betterterms-guardrails/scripts/bt.py"
        self.assertTrue(bt.is_file())
        resolved = (
            target / ".claude/skills/betterterms-exchange"
            / "../betterterms-guardrails/scripts/bt.py"
        ).resolve()
        self.assertEqual(resolved, bt.resolve())
        marker = target / ".claude/skills/.betterterms-version"
        self.assertEqual(marker.read_text().strip(), VERSION)
        for name in SKILL_NAMES:
            self.assertTrue(
                (target / ".claude/skills" / name / "SKILL.md").is_file(),
                name,
            )

    def test_vendor_is_idempotent(self):
        target = self.tmp / "consumer"
        target.mkdir()
        for _ in range(2):
            proc = run(self.repo, "vendor-into-repo", str(target),
                       home=self.home)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_vendor_refuses_missing_or_nondir(self):
        proc = run(self.repo, "vendor-into-repo",
                   str(self.tmp / "missing"), home=self.home)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        proc = run(self.repo, "vendor-into-repo", home=self.home)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)


class DoctorTest(ScriptTestCase):
    def doctor(self):
        return run(self.repo, "doctor", home=self.home)

    def test_clean_home_passes(self):
        proc = self.doctor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_doctor_detects_duplicate(self):
        write_skill(self.home / ".agents" / "skills", "betterterms-start")
        write_skill(self.home / ".claude" / "skills", "betterterms-start")
        proc = self.doctor()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("betterterms-start", proc.stdout + proc.stderr)

    def test_doctor_detects_broken_link(self):
        link = self.home / ".agents" / "skills" / "betterterms-start"
        link.symlink_to(self.tmp / "nonexistent" / "betterterms-start")
        proc = self.doctor()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("broken", (proc.stdout + proc.stderr).lower())

    def test_doctor_detects_stale_linked_version(self):
        other = self.tmp / "other-repo"
        write_skill(other / "skills", "betterterms-x")
        (other / "VERSION").write_text("9.9.9\n")
        link = self.home / ".agents" / "skills" / "betterterms-x"
        link.symlink_to((other / "skills" / "betterterms-x").resolve())
        proc = self.doctor()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("9.9.9", proc.stdout + proc.stderr)

    def test_doctor_detects_stale_copy(self):
        write_skill(self.home / ".agents" / "skills", "betterterms-start")
        marker = self.home / ".agents" / "skills" / ".betterterms-version"
        marker.write_text("9.9.9\n")
        proc = self.doctor()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("9.9.9", proc.stdout + proc.stderr)

    def test_doctor_passes_on_linked_repo_install(self):
        link = self.home / ".agents" / "skills" / "betterterms-start"
        link.symlink_to((self.repo / "skills" / "betterterms-start").resolve())
        proc = self.doctor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class ZipSkillsTest(ScriptTestCase):
    def test_zip_per_skill_deterministic(self):
        for _ in range(2):
            proc = run(self.repo, "zip-skills", home=self.home)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        dist = self.repo / "dist"
        zips = sorted(dist.glob("betterterms-*.zip"))
        self.assertEqual(len(zips), len(SKILL_NAMES))
        blob = zipfile.ZipFile(dist / "betterterms-start.zip")
        names = blob.namelist()
        self.assertIn("betterterms-start/SKILL.md", names)
        self.assertFalse(any("__pycache__" in n for n in names))
        again = self.tmp / "second"
        shutil.copytree(self.repo, again, ignore=shutil.ignore_patterns("dist"))
        proc = run(again, "zip-skills", home=self.home)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for z in zips:
            self.assertEqual(
                z.read_bytes(), (again / "dist" / z.name).read_bytes()
            )


class SessionStartHookTest(ScriptTestCase):
    def hook(self, extra_env):
        env = dict(os.environ, HOME=str(self.home))
        env.pop("BETTERTERMS_HOME", None)
        env.update(extra_env)
        return subprocess.run(
            ["sh", str(self.repo / "hooks" / "session-start.sh")],
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_prints_one_line_pointing_at_start(self):
        proc = self.hook({})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("betterterms-start", lines[0])

    def test_remote_session_silent_without_cases(self):
        bt_home = self.tmp / "bthome"
        proc = self.hook({
            "CLAUDE_CODE_REMOTE": "true",
            "BETTERTERMS_HOME": str(bt_home),
        })
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_remote_session_prints_when_case_exists(self):
        bt_home = self.tmp / "bthome"
        (bt_home / "cases" / "case-1").mkdir(parents=True)
        proc = self.hook({
            "CLAUDE_CODE_REMOTE": "true",
            "BETTERTERMS_HOME": str(bt_home),
        })
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("betterterms-start", proc.stdout)


if __name__ == "__main__":
    unittest.main()
