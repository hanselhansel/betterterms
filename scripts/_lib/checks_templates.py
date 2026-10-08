"""The shipped-template self-check (spec 4.3): every fenced block in
``skills/*/references/templates/*.md`` is a message body the agent
copies, so each one renders against the fixture case in
``tests/fixtures/template_case`` and is gated at autonomy 3 and 4.
A block that trips the gate (``block`` or ``needs_approval``) fails
with its path, so no shipped template can carry wording the gate
itself would stop. ``<slot>`` markers are agent fill-ins, not
literal output: a stand-in word replaces each before gating.
"""

import re
import shutil
import sys
import tempfile
from pathlib import Path

from .checks_scan import display, join

# Message bodies live in ```text and bare ``` fences; other fences
# (yaml examples, shell snippets) are not shipped messages.
_FENCE = re.compile(r"^```(?:text)?[ \t]*\n(.*?)^```", re.M | re.S)
_SLOT = re.compile(r"<[^>]*>")
_AUTONOMIES = (3, 4)


def _repo_root():
    return Path(__file__).resolve().parents[2]


def _btlib():
    scripts = str(
        _repo_root() / "skills" / "betterterms-guardrails" / "scripts"
    )
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from btlib import gate, yaml

    return gate, yaml


def gate_template(text, fixture_dir, inbound=None, autonomies=_AUTONOMIES):
    """``[(autonomy, result, reasons)]``: the gate verdicts for one
    template body rendered against ``fixture_dir`` at each autonomy
    level. ``<slot>`` markers are agent fill-ins, so a stand-in word
    replaces each before gating."""
    gate, yaml = _btlib()
    fixture_dir = Path(fixture_dir)
    brief = yaml.load((fixture_dir / "brief.yaml").read_text())
    if inbound is None and (fixture_dir / "inbound.yaml").is_file():
        inbound = yaml.load(
            (fixture_dir / "inbound.yaml").read_text()
        )
    try:
        floor = float((fixture_dir / ".floor").read_text().strip())
        offer = floor * 0.85
    except (OSError, ValueError):
        offer = 85
    draft = {
        "action": "send",
        "offer": offer,
        "period": "once",
        "template": _SLOT.sub("example", text),
        "claims": [],
    }
    verdicts = []
    for autonomy in autonomies:
        with tempfile.TemporaryDirectory() as td:
            case_dir = Path(td) / "case"
            shutil.copytree(fixture_dir, case_dir)
            (case_dir / "brief.yaml").write_text(
                yaml.dump(dict(brief, autonomy=autonomy))
            )
            result, reasons, _ = gate.check(
                str(case_dir), dict(draft), False, inbound
            )
        verdicts.append((autonomy, result, reasons))
    return verdicts


def check_templates_gate(root):
    """(ok, detail): every fenced block in the shipped templates
    gates clean at autonomy 3 and 4 against the fixture case."""
    root = Path(root)
    fixture = root / "tests" / "fixtures" / "template_case"
    if not fixture.is_dir():
        return False, "no tests/fixtures/template_case"
    failures = []
    for path in sorted(root.glob("skills/*/references/templates/*.md")):
        rel = path.relative_to(root)
        for i, block in enumerate(_FENCE.findall(path.read_text()), 1):
            for autonomy, result, reasons in gate_template(block, fixture):
                if result != "pass":
                    failures.append(
                        f"{display(rel)} block {i} autonomy "
                        f"{autonomy}: {result} ({'; '.join(reasons)})"
                    )
                    break
    return (not failures), join(failures)


def check_templates_gate_status(root):
    """``check_templates_gate`` as a (status, detail) verify check."""
    if not (
        Path(root) / "tests" / "fixtures" / "template_case"
    ).is_dir():
        return "SKIP", "no tests/fixtures/template_case"
    ok, detail = check_templates_gate(root)
    return ("PASS", "") if ok else ("FAIL", detail)
