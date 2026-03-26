---
name: billfree
description: "BillFree support operations via the BF-TKT API. Use when the user wants to raise a ticket, report an issue, log a complaint, or create a support request related to BillFree services (POS issues, merchant problems, billing concerns, etc.). Collects required information from the user conversationally, then calls the API. Future: get ticket status, update tickets."
---

# BillFree Support Skill

Support operations via the BillFree BF-TKT API. Currently supports creating tickets. Collects issue details from the user and raises a ticket programmatically.

## Workflow

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

For full API details, see [BF-Tkt API_DOCUMENTATION.md](BF-Tkt API_DOCUMENTATION.md).
