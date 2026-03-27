---
name: billfree
description: "BillFree support operations. Use when the user wants to raise a ticket, report an issue, log a complaint, or create a support request related to BillFree services (POS issues, merchant problems, billing concerns, etc.). Also use when the user wants a summary of the past 6 hours of conversation history in concise WhatsApp-ready bullet points. Collect required information conversationally, then either call the BF-TKT API or summarize recent session history."
---

# BillFree Support Skill

Support operations for BillFree workflows. Currently supports:

1. Creating support tickets via the BillFree BF-TKT API
2. Summarizing the past 6 hours of conversation history into a WhatsApp-ready update

Choose the workflow based on the user's request. Do not create a ticket when the user only asked for a summary. Do not summarize when the user only asked to create a ticket.

## Quick Reference

| User Need                                 | Action                                                                 |
| ----------------------------------------- | ---------------------------------------------------------------------- |
| Report issue / raise complaint / log case | Gather required details, then run `scripts/create_ticket.py`           |
| Summarize recent conversation for WhatsApp | Read the last 6 hours of conversation history and produce bullet points |

## Workflow

### Workflow A: Create a Ticket

1. **Gather information** from the user's message
2. **Check required fields** — ask follow-up if anything is missing
3. **Create the ticket** by running `create_ticket.py`
4. **Report the result** to the user

## Required & Optional Fields

| Field         | Required    | What to Collect                                      |
| ------------- | ----------- | ---------------------------------------------------- |
| `concern`     | **Yes**     | The issue description — what's wrong (max 500 chars) |
| `phone`       | Recommended | Customer's phone number (10-digit)                   |
| `requestedBy` | Optional    | Customer's name (defaults to "WhatsApp User")        |
| `mid`         | Optional    | Merchant ID — numeric only                           |
| `business`    | Optional    | Business/store name (max 200 chars)                  |
| `pos`         | Optional    | POS terminal ID (max 50 chars)                       |

## Gathering Information

Extract as much as possible from the user's initial message. Only ask a follow-up if `concern` is missing — it is the only strictly required field from the user.

**If concern is missing**, ask:

> "Could you describe the issue you're facing?"

**If phone is missing**, ask once:

> "Could you share your phone number so the support agent can reach you?"

Do NOT ask for all optional fields one by one — only ask for `concern` (if missing) and `phone` (if missing). Accept whatever other info the user volunteers.

## Creating a Ticket

```bash
python3 scripts/create_ticket.py --concern "POS machine not responding" --phone "9876543210"
```

All flags:

```bash
python3 scripts/create_ticket.py \
  --concern "POS machine not responding" \
  --phone "9876543210" \
  --name "Customer Name" \
  --mid "123456" \
  --business "ABC Store" \
  --pos "Terminal-01"
```

| Flag         | Maps to API field | Required |
| ------------ | ----------------- | -------- |
| `--concern`  | `concern`         | **Yes**  |
| `--phone`    | `phone`           | No       |
| `--name`     | `requestedBy`     | No       |
| `--mid`      | `mid`             | No       |
| `--business` | `business`        | No       |
| `--pos`      | `pos`             | No       |

## Responding to the User

**On success** (script prints ticket details):

> "Your ticket **{{ticketId}}** has been created. Our agent **{{assignedAgent}}** will contact you shortly."

**On failure** (script exits with error):

> "Unable to create the ticket right now. Please try again in a moment."

If the error code is `E001` (rate limit), wait 60 seconds before retrying.
If the error code is `E004` (validation), check the fields and correct them.

### Workflow B: Summarize the Past 6 Hours for WhatsApp

Use this workflow when the user asks for a summary, recap, update, handoff, or WhatsApp-ready message based on recent conversation history.

#### Goal

Generate a concise WhatsApp message in bullet points covering the most important topics discussed in the past 6 hours.

#### Where to Get the Conversation History

Prefer deterministic session extraction over asking the user to repeat the conversation.

OpenClaw stores the source of truth on disk:

- Session store: `~/.openclaw/agents/<agentId>/sessions/sessions.json`
- Transcript: `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`

The recommended path for this skill is to run the bundled extractor script first, then summarize its output:

```bash
python3 scripts/extract_recent_conversation.py --session-key "<current-session-key>" --hours 6
```

Useful variants:

```bash
# Target a specific session directly
python3 scripts/extract_recent_conversation.py --session-key "agent:main:whatsapp:direct:+9185..." --hours 6

# Filter by channel + peer when you know the scope exactly
python3 scripts/extract_recent_conversation.py --channel whatsapp --peer "+9185..." --hours 6

# Emit JSON if structured post-processing is needed
python3 scripts/extract_recent_conversation.py --session-key "<current-session-key>" --hours 6 --json
```

How the extractor works:

1. Reads `sessions.json`
2. Resolves the active matching session
3. Opens the referenced transcript JSONL
4. Filters messages to the last 6 hours
5. Removes OpenClaw session boilerplate and metadata wrappers
6. Prints a clean transcript for summarization

Safety rules:

- Prefer the exact current `sessionKey`
- For group chats, use that group's exact session key, for example `agent:<agentId>:whatsapp:group:<groupId>`
- For direct chats under `dmScope: "per-channel-peer"`, use the exact per-peer key, for example `agent:<agentId>:whatsapp:direct:<peerId>`
- The extractor refuses to guess from a broad "most recent session" fallback
- The extractor also refuses to read the shared `agent:<agentId>:main` session unless `--allow-main` is explicitly passed

Only fall back to direct context-only summarization if the script cannot access the OpenClaw state files. Do not ask the user to paste the conversation unless both the state files and the relevant working context are unavailable.

#### Time Window

- Only summarize messages from the last 6 hours
- Use transcript entry timestamps when available
- If the available session contains older content, ignore messages outside the 6-hour window
- Base the summary on the extractor output, not on vague recollection of earlier turns

#### What to Include

Focus on the information that matters in an operational WhatsApp update:

- Main topics discussed
- Customer or merchant issues raised
- Decisions made
- Actions taken
- Pending follow-ups
- Blockers, risks, or unresolved items
- Important identifiers only when relevant, such as ticket IDs, merchant IDs, POS IDs, or callback numbers

#### What to Exclude

- Small talk and filler
- Repetitive back-and-forth that does not change the outcome
- Internal tool chatter, raw metadata, or JSON
- Speculation not supported by the conversation

#### Output Format

The final output must be ready to send as a WhatsApp message.

Rules:

- Keep it concise and readable on mobile
- Use bullet points only
- Cover important topics first
- Prefer 4 to 8 bullets unless the conversation was extremely light or unusually dense
- Use plain language
- Do not include headings like "analysis" or "summary generated"
- Do not mention internal APIs, session IDs, or tool names in the message body

Use this format:

```text
*Last 6 Hours Summary*

• [Important topic / update]
• [Important topic / update]
• [Decision / action taken]
• [Pending follow-up / blocker]
```

If there was very little meaningful activity, say so clearly in bullet points instead of inventing content.

## Setup

The `BF_API_KEY` environment variable must be set with the BillFree API key.

## Error Reference

| Code   | Meaning                | Action                          |
| ------ | ---------------------- | ------------------------------- |
| `E001` | Rate limit / duplicate | Wait 60s, retry                 |
| `E002` | Invalid API key        | Check `BF_API_KEY`              |
| `E004` | Validation error       | Fix request fields              |
| `E006` | Server busy            | Retry after 5s                  |
| `E999` | Internal error         | Inform user to contact BillFree |

## API Documentation

For full API details, see [BF-Tkt API_DOCUMENTATION.md](_temp/BF-Tkt API_DOCUMENTATION.md).
