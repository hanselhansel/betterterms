// Gate rows in the transcript (spec 6.1): each `bt.py gate` tool row
// is redrawn as one line instead of the JSON the tool printed:
//   ✓ Gate pass            on result pass
//   ✗ Gate block: <why>    on block, error or unreadable output
//   ● Held for you         on needs_approval
// Pure: register.js hands the ToolUse props in and wraps the verdict.

import { collectStrings } from "../lib/cases.js";

// A gate call is a shell command carrying bt.py (usually as a full
// path: python3 .../scripts/bt.py gate ...) and the gate verb.
const GATE_CALL = /\bbt\.py\b/;
const GATE_VERB = /\bgate\b/;

// props: the ToolUse row's {tool, input, output, isRunning, ...}.
// Returns {text, color} for a gate row, null for anything else, so the
// hook can defer to the stock row.
export function gateRow(props) {
  const input = props?.input;
  const isGate = collectStrings(input).some(
    (s) => GATE_CALL.test(s) && GATE_VERB.test(s),
  );
  if (!isGate || props.isRunning) return null;
  const stdout = typeof props.output === "object" && props.output !== null
    ? props.output.stdout
    : props.output;
  if (typeof stdout !== "string") return null;
  let out;
  try { out = JSON.parse(stdout); } catch { out = null; }
  if (!out || typeof out !== "object") {
    return { text: "✗ Gate error: unreadable output", color: "red" };
  }
  if (out.result === "pass") return { text: "✓ Gate pass", color: "green" };
  if (out.result === "needs_approval") return { text: "● Held for you", color: "yellow" };
  const why = Array.isArray(out.reasons) && out.reasons.length > 0
    ? `: ${out.reasons.map(String).join("; ")}`
    : "";
  if (out.result === "block") return { text: `✗ Gate block${why}`, color: "red" };
  return { text: `✗ Gate error${why}`, color: "red" };
}
