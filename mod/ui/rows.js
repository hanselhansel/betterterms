// Gate rows in the transcript (spec 6.1): each `bt.py gate` tool row
// is redrawn as one line instead of the JSON the tool printed:
//   ✓ Gate pass            on result pass
//   ✗ Gate block: <why>    on block, error or unreadable output
//   ● Held for you         on needs_approval
// Pure: register.js hands the ToolUse props in and wraps the verdict.

// A gate call is one plain `bt.py gate` invocation (usually as a
// full path: python3 .../scripts/bt.py gate ...; a shlex-quoted
// path puts a closing quote between bt.py and gate). A command that
// composes anything else -- `;`, `&&`, `||`, `|`, redirection,
// command substitution, a subshell, a second line -- keeps the
// stock row: collapsing it would hide the rest of what ran.
const GATE_CALL = /\bbt\.py['"]?\s+gate\b/;
const COMPOSED = /[;|&<>`$()\r\n\\]/;

// props: the ToolUse row's {tool, input, output, isRunning, ...}.
// Only input.command, the Bash call's command string, is tested: a
// `bt.py gate` mention in the description or any other field is not
// the command that ran and keeps the stock row.
// Returns {text, color} for a gate row, null for anything else, so the
// hook can defer to the stock row.
export function gateRow(props) {
  const command = props?.input?.command;
  const isGate = typeof command === "string"
    && GATE_CALL.test(command)
    && !COMPOSED.test(command);
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
