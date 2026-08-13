# 0009 — Telegram is a conversation transport, not a notification channel

**Status:** accepted · **Amends:** D5 and ADR 0005 in part

## Context

D5 put Telegram out of scope. The reason was specific: a **proactive** channel
creates an operational commitment — a send time, a retry policy, a queue, and a
question about what happens when delivery fails at 3am — and none of that
belongs to an analysis product.

The owner has since asked for something the exclusion does not cover: the
ability to link an account and **talk to the agent** from Telegram. Not a bot
with canned replies; the agent itself.

That is a different capability from the one D5 excluded, and the difference is
not the medium. It is **who starts**. A reply is requested, immediate, and
carries nothing forward if it fails — one message is lost and nothing is left
pending anywhere. A notification is none of those things.

## Decision

Telegram becomes a **second door into the same room**: the same agent, the same
constitution, the same engines, the same tools, reached from somewhere else.

**Conversation only.** Not a single message is ever initiated by the system — no
activation alert, no daily summary, no weekly report, no invalidation notice. If
the user does not write, nothing arrives. D5 stands in full for everything it
actually excluded.

**Linking is by a one-time code minted inside the platform.** The user generates
it while authenticated in Leovee and sends it to the agent once. The agent never
asks for an email or a password over Telegram.

**The same agent, not a smaller one.** A simplified Telegram bot would be
cheaper and would produce *two* agents whose behaviour drifts, saying different
things about the same market in two windows. That is the class of gap this
migration exists to close.

## Consequences

**The guard changes shape rather than being deleted.** `test_no_execution_surface`
no longer fails the build on the string `telegram`; instead it confines the term
to the transport's own modules and its registration points, and it fails on any
function in the transport whose name reads as an outbound verb. There is exactly
one function that reaches Telegram, `reply_to`, and it takes its destination
from the inbound update. **An unsolicited send is not something to remember not
to write — there is no function that can express it.**

**Three lookups cannot run under workspace RLS**, and this is the sharpest
consequence. A webhook arrives carrying a Telegram id and nothing else; the
workspace is the *answer*, not an input. Binding RLS from the message would let
untrusted text name the workspace it wants, which is the exact escape the
tenancy model exists to prevent. They run instead through narrow
`SECURITY DEFINER` functions: one argument, a fixed projection, no
caller-controlled predicate, no enumeration. Everything after them runs under
ordinary RLS bound to what they returned.

**Membership is re-verified on every message.** The link stores a user id, and
each inbound message rebuilds the tenant context through `resolve_tenant_context`,
which checks membership in the database. A user removed from the workspace loses
Telegram access on their next message with nothing to remember to revoke.

**An unknown sender learns nothing.** Unlinked, wrong code and expired code all
get the same sentence. Distinguishing them would let anyone holding the bot's
handle probe for accounts.

**Whoever holds the Telegram account holds the agent.** No design avoids that,
so the mitigation is revocation: one click in the platform, and the row is kept
and stamped rather than deleted, because *when* the link was cut matters more
than its absence would.

## Alternatives rejected

**Polling instead of a webhook.** Needs a long-running worker owning the update
cursor, and two replicas reading the same queue fight over messages. A webhook
is stateless and fits the existing deployment.

**Email and password over Telegram.** Simpler for the user and it puts
credentials in a chat log on a device we do not control.

**A bot per user.** Perfect isolation, and far more setup friction than the
capability is worth.

## What the references contributed

From `openclaw`: *unknown senders are rejected by default and require explicit
pairing*, and *inbound messages are untrusted input*. Both are exactly what the
one-time code enforces. The message-queue pattern in
`telegram-multi-agent-ai-bot` was **not** adopted — consolidating messages over a
15-second window suits a conversational bot and would delay an analysis reply
for nothing here.
