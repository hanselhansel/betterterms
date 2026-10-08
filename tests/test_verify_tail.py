"""``checks_scan.tail`` condenses a failed subprocess into the FAIL
line's detail: stderr carries the diagnostics (unittest prints its
failure report there), so it takes priority and stdout is only the
fallback when stderr has nothing to say. A long unittest report also
contributes its FAIL/ERROR headers and traceback exception lines,
which the bare window loses to the run summary."""

import types
import unittest

# Loading test_verify execs scripts/verify, which puts scripts/ on
# sys.path; _lib then resolves to the same package verify uses.
from test_verify import checks_scan


def result(stdout="", stderr=""):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr)


class TailTest(unittest.TestCase):
    # Value: protects=the unittest report on stderr reaches the FAIL
    # line even when the failed command also wrote pages of stdout;
    # fails_when=tail concatenates stderr before stdout again, so
    # trailing stdout lines push the traceback out of the window;
    # seam=none
    def test_stderr_wins_over_noisy_stdout(self):
        r = result(
            stderr="FAIL: test_x\nAssertionError: 1 != 2\n",
            stdout="\n".join(f"build noise {i}" for i in range(20)),
        )
        out = checks_scan.tail(r)
        self.assertIn("AssertionError: 1 != 2", out)
        self.assertIn("FAIL: test_x", out)
        self.assertNotIn("build noise", out)

    def test_stdout_is_the_fallback_when_stderr_is_empty(self):
        r = result(stdout="compiler says no\ndetail line\n", stderr="")
        self.assertEqual(
            checks_scan.tail(r), "compiler says no | detail line"
        )
        r = result(stdout="only stdout\n", stderr=None)
        self.assertEqual(checks_scan.tail(r), "only stdout")

    def test_blank_stderr_falls_back_to_stdout(self):
        r = result(stdout="stdout detail\n", stderr="  \n")
        self.assertEqual(checks_scan.tail(r), "stdout detail")

    # Value: protects=a failing unittest run's FAIL header and the
    # traceback's exception line reach the FAIL detail even though the
    # "Ran N tests"/"FAILED (failures=N)" summary fills the window;
    # fails_when=tail returns only the last n lines again, so a real
    # 884-test failure reports nothing but the summary; seam=none
    def test_long_unittest_report_names_the_failure(self):
        bar = "=" * 70
        dash = "-" * 70
        stderr = "".join(
            f"test_{i} (tests.test_x.Test.test_{i}) ... ok\n"
            for i in range(880)
        )
        stderr += (
            f"{bar}\n"
            "FAIL: test_slow "
            "(tests.test_render_perf.RenderPerfTest.test_slow)\n"
            f"{dash}\n"
            "Traceback (most recent call last):\n"
            '  File "/repo/tests/test_render_perf.py", line 95, '
            "in test_slow\n"
            "    self.assertLess(elapsed, 1.0)\n"
            "AssertionError: 1.42 not less than 1.0\n"
            f"{dash}\n"
            "Ran 884 tests in 760.150s\n"
            "\n"
            "FAILED (failures=1)\n"
        )
        r = result(
            stderr=stderr,
            stdout="\n".join(f"build noise {i}" for i in range(50)),
        )
        out = checks_scan.tail(r)
        self.assertIn(
            "FAIL: test_slow "
            "(tests.test_render_perf.RenderPerfTest.test_slow)",
            out,
        )
        self.assertIn("AssertionError: 1.42 not less than 1.0", out)
        self.assertIn("FAILED (failures=1)", out)
        self.assertNotIn("build noise", out)

    def test_tail_keeps_last_n_lines(self):
        r = result(stderr="\n".join(f"e{i}" for i in range(10)))
        self.assertEqual(checks_scan.tail(r), "e5 | e6 | e7 | e8 | e9")
        self.assertEqual(checks_scan.tail(r, n=2), "e8 | e9")
        self.assertEqual(checks_scan.tail(result()), "")


if __name__ == "__main__":
    unittest.main()
