// The AbovePrompt band (spec 6.1): drawn only while something needs
// the user — a held draft, a gate-passed draft not yet sent, or a
// fresh inbound reply. One line plus a Review button (hotkey 2, the
// pane tab it opens) that jumps to Approvals.

import * as C from "../lib/cases.js";

// counts: {held, pending, repliers}. el: the resolved element set.
// onReview: the press handler for the Review button.
export function bandTree(el, counts, onReview) {
  const text = C.bandText(counts.held ?? 0, counts.pending ?? 0, counts.repliers ?? []);
  if (text === "") return null;
  const { Box, Text, Button } = el;
  return h(
    Box,
    null,
    h(Text, { dimColor: true }, text),
    h(Text, null, " "),
    h(Button, {
      key: "review",
      label: "Review",
      hotkey: "2",
      plain: true,
      onPress: onReview,
    }),
  );
}
