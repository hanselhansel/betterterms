// Send-shape tests for lib/cases.js sendShapeError, the rule that
// decides whether a tool call may carry the freshly gated text.
// Run: node --test mod/
//
// Default deny with an exact key allowlist (keys normalize by
// lowering case and stripping "_" and "-"): exactly one string leaf,
// under any key, equals the rendered text (normalized). Address keys
// (to, cc, bcc, recipient, recipients, email) take whitespace-free
// strings or arrays of them. Id keys (channel, channelid, threadts,
// threadid, messageid, replythreadid, replytomessageid, inreplyto,
// references, conversationid, chatid, draftid) take whitespace-free
// strings or numbers. subject/title are empty or `Re: ` plus clean
// text. Any other key, any nested key outside these sets, and any
// boolean or null under a non-allowlisted key denies. Bash is never
// a send.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as C from "./lib/cases.js";
import { RENDERED } from "./testkit.js";

const send = (tool, args) => ({ tool, tool_use_id: "t", ...args });
const shape = (args, tool = "gmail.send") =>
  C.sendShapeError(send(tool, args), RENDERED);

describe("sendShapeError", () => {
  test("the gated text fills exactly one argument", () => {
    assert.equal(shape({ to: "v@x", subject: "Re: plan", body: RENDERED }), null);
    assert.match(shape({ to: "v@x" }), /verbatim/);
    assert.match(shape({ body: RENDERED, text: RENDERED }), /more than one/);
    // Whitespace-only differences still match the render, and the
    // text leaf is allowed under any key.
    assert.equal(shape({ body: RENDERED.replace("\n", "   ") }), null);
    assert.equal(shape({ payload: RENDERED }), null);
    // The text inside a longer argument denies.
    assert.match(
      shape({ body: `see below\n${RENDERED}` }),
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

  test("the three real send shapes pass", () => {
    for (const args of [
      // Gmail reply: the message id under a camelCase id key.
      { messageId: "<abc123@mail.gmail.com>", body: RENDERED },
      // Gmail thread send: recipient, `Re: ` subject, thread id.
      {
        to: "vendor@x", subject: "Re: your renewal", body: RENDERED,
        replyThreadId: "thread-9917",
      },
      // Slack: snake_case channel and thread ts, the text as message.
      { channel_id: "C0123AB", thread_ts: "1728000000.000100", message: RENDERED },
      // Replies carry their id fields in more spellings.
      { in_reply_to: "<m-1@x>", body: RENDERED },
      { replyToMessageId: "m-2", body: RENDERED },
      { conversationId: "conv42", draftId: "d-7", body: RENDERED },
      { cc: ["a@x", "b@y"], text: RENDERED },
      { bcc: "log@x", references: "<a@x>", body: RENDERED },
      { recipient: "v@x", recipients: "w@x", email: "v@x", channel: "#re", body: RENDERED },
      // A numeric id is still an id (a chat id may arrive as a number).
      { chat_id: -1001, body: RENDERED },
      { threadId: 9917, body: RENDERED },
    ]) {
      assert.equal(shape(args), null, JSON.stringify(args));
    }
  });

  test("address and id leaves must be whitespace-free", () => {
    for (const [args, key] of [
      [{ to: "v@x or whoever", body: RENDERED }, "to"],
      [{ to: ["a@x", "b @y"], body: RENDERED }, "to"],
      [{ cc: 1200, body: RENDERED }, "cc"],
      [{ references: "<a@x> <b@x>", body: RENDERED }, "references"],
      [{ conversation_id: "conv 42", body: RENDERED }, "conversation_id"],
      [{ messageId: "a b", body: RENDERED }, "messageId"],
      [{ channel: ["#a", "#b c"], body: RENDERED }, "channel"],
      [{ chat_id: true, body: RENDERED }, "chat_id"],
      [{ thread_ts: null, body: RENDERED }, "thread_ts"],
    ]) {
      assert.match(shape(args), new RegExp(`'${key}'`), JSON.stringify(args));
    }
  });

  test("subject and title take `Re: ` plus a clean header line", () => {
    assert.equal(shape({ subject: "Re: the plan", body: RENDERED }), null);
    assert.equal(shape({ subject: "Re: your renewal", to: "v@x", body: RENDERED }), null);
    assert.equal(shape({ subject: "", body: RENDERED }), null);
    assert.equal(shape({ subject: null, body: RENDERED }), null);
    for (const value of [
      // Only an exact `Re: ` prefix (or empty) carries a header.
      "re: the plan",
      "RE: the plan",
      "Agreed, sixty two thousand works",
      "Accepted",
      "Your renewal",
      "Re: invoice 42",
      "Re: the 20 plan",
      "Re: sixty two thousand",
      "Re: it costs one hundred",
      "Re: counter at 5k",
      "Re: we accept",
      "Re: agreed terms",
      "Re: a deal",
      "Re: signed copy",
      "Re: cancel now",
      "Re: payment terms",
      "Re: offering",
      "Re: confirmed",
      "Re: yes please",
      `Re: ${"s ".repeat(40)}s`,
      "Re:missing space after the colon",
      "Re: about k more",
    ]) {
      assert.match(
        shape({ subject: value, body: RENDERED }),
        /'subject'/,
        value,
      );
    }
    assert.match(shape({ title: "Re: yes", body: RENDERED }), /'title'/);
    assert.equal(shape({ title: "Re: the plan", body: RENDERED }), null);
  });

  test("every probe under a non-allowlisted key denies, naming the key", () => {
    for (const [args, key] of [
      [{ bid: 62000, body: RENDERED }, "bid"],
      [{ amounts: "62000", body: RENDERED }, "amounts"],
      [{ paid: "62000", body: RENDERED }, "paid"],
      [{ contents: "Yes,62000,final", body: RENDERED }, "contents"],
      [{ posts: "accept-62k", body: RENDERED }, "posts"],
      [{ headers: { "X-Accept-62000": "" }, body: RENDERED }, "X-Accept-62000"],
      [{ flags: { "we-accept-62000": true }, body: RENDERED }, "we-accept-62000"],
      // The key classes of the old rule deny by key now: content
      // keys, id-suffix keys and empty fields alike.
      [{ htmlBody: "<p>hi</p>", body: RENDERED }, "htmlBody"],
      [{ htmlBody: "", body: RENDERED }, "htmlBody"],
      [{ attachments: ["f.pdf"], body: RENDERED }, "attachments"],
      [{ note: "", body: RENDERED }, "note"],
      [{ batch_ts: "1728000000000", body: RENDERED }, "batch_ts"],
      [{ from: "me@x", body: RENDERED }, "from"],
      [{ urgent: false, body: RENDERED }, "urgent"],
      [{ extra: null, body: RENDERED }, "extra"],
      [{ dryRun: true, body: RENDERED }, "dryRun"],
    ]) {
      assert.match(shape(args), new RegExp(`'${key}'`), JSON.stringify(args));
    }
    // An empty array or object carries no leaf, so nothing denies.
    assert.equal(shape({ attachments: [], headers: {}, body: RENDERED }), null);
  });
});
