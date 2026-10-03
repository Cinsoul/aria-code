# Channel Apps

Target role: adapters for non-terminal entrypoints.

Examples:

- relay server/client;
- Feishu bot;
- Telegram bot;
- webhooks;
- future desktop or browser UI.

Each channel should translate inbound messages into gateway requests and render
gateway responses back to the channel. It should not bypass safety, runtime, or
artifact policies.

## The conversation layer (`conversation.py`)

Everything a chat bot decides that does not depend on the platform lives in
one module, so every channel — Feishu today, Arthera's own bot later — gets
the same rules from the same code:

| Rule | Where |
|------|-------|
| In a group, answer only when addressed; in a direct chat, always | `should_respond` |
| One group = one shipper (货主), bound by an admin with `/owner <id>` | `handle_owner_command`, `ConversationStore` |
| Admins are per channel: `ARIA_CHANNEL_ADMINS=feishu:ou_x,telegram:42` | `is_admin` |
| Context is the conversation's own recent messages, never another's; capped at 20 messages and 7 days | `ConversationStore.history` |
| A bound conversation runs every turn with `ARIA_OWNER_SCOPE`, enforced by the logistics tools themselves | `ChannelTurn.env`, `tools/logistics_tenancy.py` |

A new channel is an adapter: turn the platform's event into an
`InboundMessage`, then

```python
if not should_respond(msg):
    return
reply = handle_owner_command(msg, store)          # /owner commands
if reply is None:
    turn = prepare_turn(msg, store)               # context + shipper scope
    reply = await run_model(turn.prompt, history=turn.history, env=turn.env)
    store.record(msg.key, "assistant", reply)
send(reply)
```

`aria_feishu_bot.feishu_inbound` is the Feishu version of that first step.
Conversation keys are `<channel>:<conversation id>`, so the same chat id on
two platforms is two conversations.
