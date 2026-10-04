// Send-shape tests for lib/cases.js sendShapeError, the rule that
// decides whether a tool call may carry the freshly gated text.
// Run: node --test mod/
//
// One uniform rule by key class: exactly one string argument equals
// the rendered text (normalized); address/id keys take a
// whitespace-free token; subject/title take a short clean header;
// content keys deny when non-empty; every other non-empty string or
// numeric leaf denies. Bash is never a send.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as C from "./lib/cases.js";
import { RENDERED } from "./testkit.js";

const send = (tool, args) => ({ tool, tool_use_id: "t", ...args });
const shape = (args, tool = "gmail.send") =>
  C.sendShapeError(send(tool, args), RENDERED);

describe("sendShapeError", () => {
  test("the gated text fills exactly one argument", () => {
    assert.equal(shape({ to: "v@x", subject: "re: plan", body: RENDERED }), null);
    assert.match(shape({ to: "v@x" }), /verbatim/);
    assert.match(shape({ body: RENDERED, text: RENDERED }), /more than one/);
    // Whitespace-only differences still match the render.
    assert.equal(shape({ body: RENDERED.replace("\n", "   ") }), null);
    // The text inside a longer argument denies.
    assert.match(
      shape({ command: `mail v@x <<EOF\n${RENDERED}\nEOF` }),
      /whole argument/,
    );
  });

  test("a Bash call is never a send", () => {
    for (const command of [`mail v@x <<EOF\n${RENDERED}\nEOF`, RENDERED]) {
      const err = C.sendShapeError(send("Bash", { command }), RENDERED);
      assert.match(err, /send tool/);
      assert.match(err, /hand .* to the user/);
    }
  });

  test("address and id keys take any whitespace-free value", () => {
    for (const args of [
      // Gmail reply: the message id under a camelCase id key.
      { messageId: "<abc123@mail.gmail.com>", body: RENDERED },
      // Gmail thread send: recipient, short subject, thread id.
      {
        to: "vendor@x", subject: "Your renewal", body: RENDERED,
        replyThreadId: "thread-9917",
      },
      // Slack: snake_case channel and thread ts (a numeric string).
      { channel_id: "C0123AB", thread_ts: "1728000000.000100", message: RENDERED },
      { in_reply_to: "<m-1@x>", body: RENDERED },
      { cc: ["a@x", "b@y"], text: RENDERED },
      { bcc: "log@x", from: "me@x", references: "<a@x>", body: RENDERED },
      { recipient: "v@x", recipients: "w@x", email: "v@x", channel: "#re", body: RENDERED },
      // Keys ending in id/ids/ts count wherever they appear.
      { conversationId: "conv42", body: RENDERED },
      { batch_ts: "1728000000000", body: RENDERED },
      // A numeric id is still an id (a chat id may arrive as a number).
      { chat_id: -1001, body: RENDERED },
      // An empty field carries nothing.
      { body: RENDERED, note: "" },
    ]) {
      assert.equal(shape(args), null, JSON.stringify(args));
    }
  });

  test("an id key still refuses whitespace, links, entities and invisible characters", () => {
    for (const args of [
      { cc: "https://pay.x/?offer=1200", body: RENDERED },
      { to: "v@x or whoever", body: RENDERED },
      { to: ["a@x", "b @y"], body: RENDERED },
      { conversation_id: "conv 42", body: RENDERED },
      { messageId: "a\u200Bb", body: RENDERED },
      { channel_id: "C%20", body: RENDERED },
      { references: "<a@x> <b@x>", body: RENDERED },
    ]) {
      assert.match(shape(args), /carries text the gate never saw/, JSON.stringify(args));
    }
  });

  test("subject and title are checked before any other shortcut", () => {
    assert.equal(shape({ subject: "re: the plan", body: RENDERED }), null);
    assert.equal(shape({ subject: "Your renewal", to: "v@x", body: RENDERED }), null);
    // Only whole words count: "signed" is not "sign".
    assert.equal(shape({ subject: "re: your plan, signed copy", body: RENDERED }), null);
    for (const [key, value] of [
      ["subject", "Accept-$40/mo"],
      ["subject", "We accept your offer"],
      ["subject", "invoice 42"],
      ["subject", `s ${"s ".repeat(40)}s`],
      // Whitespace-free does not exempt a subject: the title rule
      // runs first.
      ["subject", "s".repeat(81)],
      ["subject", "a & b"],
      ["subject", "half % off"],
      ["subject", "see https://x"],
      ["subject", "pick <one>"],
      ["subject", "ok\u200Bhere"],
      ["title", "sign the deal"],
      ["title", "cancel now"],
      ["title", "pay today"],
      ["title", "do you agree?"],
      ["title", "an offer"],
    ]) {
      assert.match(
        shape({ [key]: value, body: RENDERED }),
        new RegExp(`'${key}'`),
        `${key}=${value}`,
      );
    }
  });

  test("content-bearing keys deny when non-empty", () => {
    for (const args of [
      { body: RENDERED, htmlBody: "<p>hi&nbsp;</p>" },
      { body: RENDERED, htmlBody: "plain text" },
      { body: RENDERED, html: "<br>" },
      { body: RENDERED, content: "a note" },
      { body: RENDERED, blocks: ["a block"] },
      { body: RENDERED, attachments: ["f.pdf"] },
      { body: RENDERED, body2: "p.s." },
      { body: RENDERED, textHtml: "q" },
    ]) {
      assert.match(shape(args), /carries content/, JSON.stringify(args));
    }
    // The same keys empty carry nothing.
    assert.equal(shape({ body: RENDERED, htmlBody: "", attachments: [] }), null);
  });

  test("every other non-empty string or numeric leaf denies", () => {
    for (const args of [
      { body: RENDERED, amount: "1200" },
      { body: RENDERED, amount: 1200 },
      { body: RENDERED, note: "accept_1200" },
      { body: RENDERED, note: "ok\u200B" },
      { body: RENDERED, note: "and a word more" },
      { body: RENDERED, retries: 2 },
      { body: RENDERED, extra: "x" },
    ]) {
      assert.match(
        shape(args),
        /carries (text|a number) the gate never saw/,
        JSON.stringify(args),
      );
    }
  });
});
