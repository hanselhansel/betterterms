// betterterms-mod's contract: the $.state values the cockpit holds for
// the session, declared so validation can name them and hooks get them
// typed.
//
//   tab        the pane's selected tab (1 Cases, 2 Approvals, 3 Savings)
//   selected   the expanded case id on the Cases tab
export type BtTab = 1 | 2 | 3;

declare module 'claude-code' {
  interface PluginState {
    'betterterms-mod': {
      tab: BtTab;
      selected: string | null;
    };
  }
}
