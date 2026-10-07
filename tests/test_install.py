import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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
    def test_no_hooks_vendors_skills_and_writes_version_marker(self):
        target = self.tmp / "consumer"
        (target / ".git").mkdir(parents=True)
        proc = run(self.repo, "vendor-into-repo", str(target),
                   "--no-hooks", home=self.home)
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
        self.assertFalse((target / ".claude" / "betterterms").exists())
        self.assertFalse(
            (target / ".claude" / "settings.json").exists()
        )

    def test_default_vendors_skills_hooks_and_settings(self):
        """Repo-declared plugins never load in cloud sessions, so the
        default vendors the pieces a session reads: the skills, the
        hook scripts, and the hook entries in settings.json."""
        target = self.tmp / "consumer"
        (target / ".git").mkdir(parents=True)
        proc = run(self.repo, "vendor-into-repo", str(target),
                   home=self.home)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(
            (
                target
                / ".claude/skills/betterterms-guardrails/scripts/bt.py"
            ).is_file()
        )
        for name in ("prompt_commands.py", "_btpath.py",
                     "session-start.sh"):
            self.assertTrue(
                (
                    target / ".claude/betterterms/hooks" / name
                ).is_file(),
                name,
            )
        settings = json.loads(
            (target / ".claude" / "settings.json").read_text()
        )
        self.assertNotIn("enabledPlugins", settings)
        events = settings["hooks"]
        self.assertEqual(
            [h["command"] for e in events["UserPromptSubmit"]
             for h in e["hooks"]],
            [
                'python3 "$CLAUDE_PROJECT_DIR/.claude/betterterms/'
                'hooks/prompt_commands.py"'
            ],
        )
        self.assertEqual(
            [h["command"] for e in events["SessionStart"]
             for h in e["hooks"]],
            [
                'bash "$CLAUDE_PROJECT_DIR/.claude/betterterms/'
                'hooks/session-start.sh"'
            ],
        )

    def test_default_notes_a_stale_enabled_plugins_entry(self):
        # A settings file written by the old vendor run enables the
        # plugin; that never loads in cloud and would load the skills
        # twice locally, so the script says so and keeps the key.
        target = self.tmp / "consumer"
        settings = target / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {"enabledPlugins": {"betterterms@betterterms": True}}
            )
        )
        proc = run(self.repo, "vendor-into-repo", str(target),
                   home=self.home)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("enabledPlugins", proc.stdout)
        self.assertTrue(
            json.loads(settings.read_text())["enabledPlugins"]
            ["betterterms@betterterms"]
        )

    def test_vendor_is_idempotent(self):
        target = self.tmp / "consumer"
        target.mkdir()
        for _ in range(2):
            proc = run(self.repo, "vendor-into-repo", str(target),
                       "--no-hooks", home=self.home)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_vendor_refuses_missing_or_nondir(self):
        proc = run(self.repo, "vendor-into-repo",
                   str(self.tmp / "missing"), home=self.home)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        proc = run(self.repo, "vendor-into-repo", home=self.home)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)


class DoctorTest(ScriptTestCase):
    def doctor(self, extra_env=None):
        return run(self.repo, "doctor", home=self.home,
                   extra_env=extra_env)

    def test_doctor_flags_native_windows(self):
        """Decision E: bt.py uses Unix file locking, so doctor reports
        native Windows as unsupported (WSL reports linux and passes)."""
        proc = self.doctor({"BETTERTERMS_PLATFORM": "win32"})
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Windows", proc.stdout)
        proc = self.doctor({"BETTERTERMS_PLATFORM": "linux"})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

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


MARKER = "betterterms: typed bt commands are active in this session."


class SessionStartHookTest(ScriptTestCase):
    def hook(self, extra_env):
        env = dict(os.environ, HOME=str(self.home))
        env.pop("BETTERTERMS_HOME", None)
        env.pop("CLAUDE_CODE_REMOTE", None)
        env.update(extra_env)
        return subprocess.run(
            ["sh", str(self.repo / "hooks" / "session-start.sh")],
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_no_cases_prints_only_the_marker(self):
        # The skills offer typed `bt` commands only when the marker is
        # in context, so it prints even before any case exists, in a
        # plain session or a remote one.
        for extra_env in ({}, {"CLAUDE_CODE_REMOTE": "true"}):
            proc = self.hook(extra_env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), MARKER)

    def test_cases_add_the_start_line(self):
        (self.home / ".betterterms" / "cases" / "case-1").mkdir(
            parents=True
        )
        proc = self.hook({})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(MARKER, proc.stdout)
        self.assertIn("betterterms-start", proc.stdout)
        self.assertNotIn("vanish", proc.stdout)

    def test_remote_session_prints_marker_without_cases(self):
        bt_home = self.tmp / "bthome"
        proc = self.hook({
            "CLAUDE_CODE_REMOTE": "true",
            "BETTERTERMS_HOME": str(bt_home),
        })
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), MARKER)

    def test_remote_session_prints_all_lines_when_case_exists(self):
        bt_home = self.tmp / "bthome"
        (bt_home / "cases" / "case-1").mkdir(parents=True)
        proc = self.hook({
            "CLAUDE_CODE_REMOTE": "true",
            "BETTERTERMS_HOME": str(bt_home),
        })
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(MARKER, proc.stdout)
        self.assertIn("betterterms-start", proc.stdout)
        self.assertNotIn("vanish", proc.stdout)

    def test_remote_session_warns_when_home_is_ephemeral(self):
        # Decision F: a cloud home vanishes with the VM, so the
        # default ~/.betterterms location gets a one-line warning
        # when a case exists to lose.
        (self.home / ".betterterms" / "cases" / "case-1").mkdir(
            parents=True
        )
        proc = self.hook({"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("vanish", proc.stdout)
        self.assertIn(MARKER, proc.stdout)
        self.assertIn("betterterms-start", proc.stdout)

    def test_remote_session_warns_with_home_relative_bt_home(self):
        bt_home = self.home / ".betterterms"
        (bt_home / "cases" / "case-1").mkdir(parents=True)
        proc = self.hook({
            "CLAUDE_CODE_REMOTE": "true",
            "BETTERTERMS_HOME": str(bt_home),
        })
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("vanish", proc.stdout)

    def test_remote_session_no_warning_without_cases(self):
        # Nothing exists to lose yet, so the vanish warning and the
        # start pointer stay quiet; the marker still prints.
        proc = self.hook({"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("vanish", proc.stdout)
        self.assertEqual(proc.stdout.strip(), MARKER)

    def test_remote_session_no_warning_for_persistent_home(self):
        # A BETTERTERMS_HOME outside the ephemeral home (a mounted
        # volume) persists, so no warning line is due.
        proc = self.hook({
            "CLAUDE_CODE_REMOTE": "true",
            "BETTERTERMS_HOME": str(self.tmp / "bthome"),
        })
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("vanish", proc.stdout)
        self.assertIn(MARKER, proc.stdout)


if __name__ == "__main__":
    unittest.main()
