"""HTML widget fragments for cloud sessions (spec 6.8).

Mod hooks draw the cockpit in Claude Code terminal and Desktop; a
Projects thread cannot host the pane, so each ``bt.py widget``
command prints ``{"html": ...}``: a self-contained fragment built
from the shipped templates under ``assets/widgets/`` which the agent
posts as is. Buttons call ``sendPrompt`` with the typed-command
grammar (``bt approve``, ``bt reject``, ``bt floor``, ``bt terms``);
``sendPrompt`` only fills the user's message box, so every widget
with buttons shows "Then press Enter to send." beside them.

The terms widget reports the walk-away as "set" or "not set" from
the file's existence alone: it never opens ``.floor``, because the
agent would have to read the value to prefill it.
"""

import html
import os
import re
import stat
from pathlib import Path

from . import BtError, MAX_TEXT, PERIODS, cases, held, ledger, render, yaml

PRESS_ENTER = "Then press Enter to send."

_TEMPLATES = Path(__file__).resolve().parents[2] / "assets" / "widgets"
_SLOT = re.compile(r"\{\{([a-z0-9_]+)\}\}")

# One shared style block, injected into every template through the
# ``{{css}}`` slot so the shipped fragments stay identical in shape.
# Light and dark tokens ride on prefers-color-scheme.
_CSS = """\
.bt-w{font:15px/1.45 -apple-system,"Segoe UI",sans-serif;max-width:34em;padding:12px;border:1px solid var(--bt-line);border-radius:8px;background:var(--bt-bg);color:var(--bt-fg);--bt-bg:#fff;--bt-fg:#1b1b1b;--bt-muted:#555;--bt-line:#d8d8d8;--bt-chip:#f1f1f1;--bt-accent:#0a7d4a;--bt-warn:#b00020}
@media (prefers-color-scheme:dark){.bt-w{--bt-bg:#1c1c1e;--bt-fg:#ececec;--bt-muted:#9a9a9a;--bt-line:#48484a;--bt-chip:#2c2c2e;--bt-accent:#34c07c;--bt-warn:#ff6b6b}}
.bt-w h3{margin:0 0 8px;font-size:14px}
.bt-chip{display:inline-block;background:var(--bt-chip);border-radius:4px;padding:1px 7px;margin:0 4px 4px 0;font-size:12px}
.bt-muted{color:var(--bt-muted);font-size:12px}
.bt-body{white-space:pre-wrap;word-break:break-word;border:1px solid var(--bt-line);border-radius:6px;background:var(--bt-chip);padding:8px;margin:8px 0}
.bt-card{border-top:1px solid var(--bt-line);padding:7px 0}
.bt-card:first-of-type{border-top:0}
.bt-w button{font:inherit;padding:4px 12px;margin:5px 8px 0 0;border:1px solid var(--bt-line);border-radius:6px;background:var(--bt-chip);color:var(--bt-fg);cursor:pointer}
.bt-w button.bt-primary{border-color:var(--bt-accent)}
.bt-w input{font:inherit;width:9em;padding:3px 7px;border:1px solid var(--bt-line);border-radius:4px;background:var(--bt-bg);color:var(--bt-fg)}
.bt-w table{border-spacing:0 6px}
.bt-reason{color:var(--bt-warn);margin:2px 0}
.bt-actions{margin-top:8px}
"""


def _esc(value):
    """Every value that enters a fragment is escaped: rendered text
    can carry a counterparty's markup through a ``{quote:n}``
    placeholder, and a raw ``<script>`` must never reach the post."""
    return html.escape(str(value), quote=True)


def _fill(name, slots):
    """Render ``<name>.html`` with ``{{slot}}`` substitution. An
    unresolved slot is an error, never silent. The fragment stays
    under the same 64 KB bound the gate applies to message text."""
    path = _TEMPLATES / f"{name}.html"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise BtError(f"widget template {name}: {e}") from e
    slots = {"css": _CSS, "press_enter": PRESS_ENTER, **slots}

    def sub(m):
        key = m.group(1)
        if key not in slots:
            raise BtError(f"widget template {name}: unknown slot {key!r}")
        return slots[key]

    out = _SLOT.sub(sub, text)
    if len(out.encode("utf-8")) > MAX_TEXT:
        raise BtError(f"widget {name}: html over 64 KB")
    return out


def _floor_state(case_dir):
    """``set`` or ``not set`` from the file's existence and shape only,
    matching read_floor's regular-file rule without opening it."""
    try:
        st = os.lstat(Path(case_dir) / ".floor")
    except OSError:
        return "not set"
    return "set" if stat.S_ISREG(st.st_mode) else "not set"


def _num(value):
    """A plain number for an input prefill: ``80`` or ``80.5``."""
    v = cases.num(value)
    if v is None:
        return ""
    return str(int(v)) if float(v).is_integer() else str(v)


def _chip(text):
    return f"<span class='bt-chip'>{_esc(text)}</span>"


def _plan_display(plan, brief):
    """(currency, period) for money display, with broken keys read as
    defaults so the widget still draws for a plan the gate would
    reject."""
    try:
        currency = cases.currency_of(plan, brief)
    except BtError:
        currency = "USD"
    try:
        period = cases.plan_period(plan)
    except BtError:
        period = "once"
    return currency, period


def _case_row(d):
    try:
        brief = cases.load_brief(d)
        plan = cases.load_plan(d)
    except BtError:
        return (
            f"<div class='bt-card'><b>{_esc(d.name)}</b>"
            "<div class='bt-muted'>case files unreadable</div></div>"
        )
    chips = "".join(
        _chip(brief[k]) for k in ("pack", "mode", "direction") if brief.get(k)
    )
    if brief.get("autonomy") is not None:
        chips += _chip(f"autonomy {brief['autonomy']}")
    currency, period = _plan_display(plan, brief)
    bits = []
    target = cases.positive(plan.get("target"))
    if target is not None:
        bits.append(f"target {_esc(render.money_text(target, period, currency))}")
    try:
        n_held = len(held.list_held(d))
        if n_held:
            bits.append(
                f"{n_held} draft{'s' if n_held > 1 else ''} waiting"
            )
    except (BtError, yaml.Error):
        bits.append("held list unreadable")
    bits.append(f"walk-away {_floor_state(d)}")
    summary = " · ".join(bits)
    return (
        f"<div class='bt-card'><b>{_esc(d.name)}</b> {chips}"
        f"<div class='bt-muted'>{summary}</div></div>"
    )


def cases_widget():
    """The cases view: one card per case folder, chips for pack, mode,
    direction and autonomy, plus target, held-draft count and
    walk-away state."""
    root = cases.home() / "cases"
    rows = []
    if root.is_dir():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            rows.append(_case_row(d))
    body = "".join(rows) or "<p class='bt-muted'>No cases yet.</p>"
    return _fill("cases", {"rows": body})


def approval_widget(d, case_id, hash8):
    """One held draft as an approval card: the rendered text, the
    gate's reasons, and Approve/Reject buttons that fill the user's
    message box with the typed command."""
    h = held.resolve(d, hash8)
    record = next(
        (e for e in held.list_held(d) if str(e.get("hash")) == h), None
    )
    if record is None:
        raise BtError(f"held draft {h[:8]} unreadable")
    reasons = record.get("reasons")
    items = "".join(
        f"<li class='bt-reason'>{_esc(r)}</li>"
        for r in reasons
    ) if isinstance(reasons, list) and reasons else (
        "<li class='bt-muted'>held for review</li>"
    )
    status = _chip("approved") if record.get("approved") else ""
    return _fill(
        "approval",
        {
            "case_id": _esc(case_id),
            "hash8": _esc(h[:8]),
            "held_at": _esc(record.get("held_at") or ""),
            "rendered": _esc(record.get("rendered") or ""),
            "reasons": items,
            "status": status,
        },
    )


def terms_widget(d, case_id):
    """The terms editor: target and best alternative prefilled from
    plan.yaml, the walk-away as an empty field plus a set or not set
    note. Its Save buttons type ``bt terms`` and ``bt floor``."""
    brief = cases.load_brief(d)
    plan = cases.load_plan(d)
    currency, period = _plan_display(plan, brief)
    target = cases.positive(plan.get("target"))
    alt = plan.get("best_alternative")
    alt = alt if isinstance(alt, dict) else {}
    alt_amount = cases.positive(alt.get("amount"))
    alt_period = str(alt.get("period") or "").lower()
    if alt_period not in PERIODS:
        alt_period = "once"
    target_now = (
        render.money_text(target, period, currency)
        if target is not None
        else "not set"
    )
    alt_now = (
        render.money_text(alt_amount, alt_period, currency)
        if alt_amount is not None
        else "not set"
    )
    if alt.get("note"):
        alt_now += f" ({alt['note']})"
    return _fill(
        "terms",
        {
            "case_id": _esc(case_id),
            "target": _esc(_num(target)),
            "alternative": _esc(_num(alt_amount)),
            "target_now": _esc(target_now),
            "alternative_now": _esc(alt_now),
            "floor_state": _esc(_floor_state(d)),
        },
    )


def savings_widget():
    """The savings view: totals per currency and per pack from the
    ledger, plus the recorded-case count. One-time savings sit in
    ``once_by_*`` and display as their own "once" amounts, never
    folded into the per-year figures."""
    totals = ledger.total()
    rows = []
    for currency, saved in totals["by_currency"].items():
        amount = (
            render.money_text(saved, "year", currency)
            if len(currency) == 3 and currency.isalpha()
            else str(saved)
        )
        rows.append(
            f"<div class='bt-card'><b>{_esc(amount)}</b>"
            f" saved per year <span class='bt-muted'>{_esc(currency)}</span></div>"
        )
    for currency, saved in totals.get("once_by_currency", {}).items():
        amount = (
            render.money_text(saved, None, currency)
            if len(currency) == 3 and currency.isalpha()
            else str(saved)
        )
        rows.append(
            f"<div class='bt-card'><b>{_esc(amount)}</b>"
            f" saved once <span class='bt-muted'>{_esc(currency)}</span></div>"
        )
    for pack, amounts in totals["by_pack"].items():
        parts = ", ".join(
            f"{_esc(c)} {_esc(v)}" for c, v in amounts.items()
        )
        rows.append(
            f"<div class='bt-muted'>{_esc(pack)}: {parts}</div>"
        )
    for pack, amounts in totals.get("once_by_pack", {}).items():
        parts = ", ".join(
            f"{_esc(c)} {_esc(v)} once" for c, v in amounts.items()
        )
        rows.append(
            f"<div class='bt-muted'>{_esc(pack)} (once): {parts}</div>"
        )
    n = totals["cases"]
    summary = f"{n} case{'s' if n != 1 else ''} recorded"
    if totals["warnings"]:
        w = totals["warnings"]
        summary += f" · {w} unreadable line{'s' if w != 1 else ''} skipped"
    return _fill(
        "savings",
        {
            "rows": "".join(rows) or "<p class='bt-muted'>Nothing recorded yet.</p>",
            "summary": _esc(summary),
        },
    )
