# grokbot-local-forms

Instructions for an assistant setting up local HTML forms for [Grok Bot](https://grok.com).

These forms stay on the person's computer. Submit saves answers as a markdown note and a matching JSON record, then notifies the Grok Bot assistant named in `target_bot`. Do the mechanical steps yourself. Ask the person only when a value is hidden from you or you need a preference you cannot infer.

## What you can do

- Clone this repository onto their computer (or copy the files they already have).
- Copy `webhook.local.json.example` to `webhook.local.json` in the repository root if that file does not exist.
- Create a webhook routine on their Grok Bot assistant if they do not already have one (a name like "Form submission handoff" is fine).
- Start `python example-form/server.py` and open `http://127.0.0.1:8765/` in their browser.
- Build new forms by copying `example-form/`, changing the questions, the `form` id, and `target_bot`.
- After webhook config exists, treat Submit as automatic: save files and ping the requesting bot. Do not ask them to go tell the other bot that the form is in.

## What you must ask the person

1. Webhook URL and key. Grok Bot does not show webhook keys to assistants, so you cannot fill `webhook.local.json` yourself. Open that file on their computer. Ask them to copy the routine's **Webhook URL** and **Webhook key** into it and save. Tell them not to paste the key into chat. They do not need the Authorization header; the server already sends `Authorization: Bearer` plus the key. This is one time. Do not repeat it for every form.
2. Where to save submissions, if it matters. Answers are ordinary files. If they use [Obsidian](https://obsidian.md), ask which vault folder to use (a `Forms` folder works well) and set `FORMS_DIR` there. If they do not use Obsidian, do not require it. Use the default `example-form/submissions` folder, or any local folder they prefer. If they want Obsidian and do not have it, point them to https://obsidian.md.

Never commit `webhook.local.json`. Never log or quote the key.

## How submissions are stored

Each Submit writes two files that share a timestamped stem, for example:

- `2026-11-09-003140-example-form.md` — readable log for the person (Obsidian or any text editor)
- `2026-11-09-003140-example-form.json` — the same answers as structured fields

Markdown is for reading. JSON is easier for an agent to parse without guessing at headings or formatting. The webhook also posts that JSON to the requesting bot at Submit time. The on-disk `.json` is a spare copy if a ping fails or something rereads the folder later.

## Setup

1. Clone this repository.
2. Copy `webhook.local.json.example` to `webhook.local.json` in the repository root.
3. Create or open their Grok Bot webhook routine.
4. Open `webhook.local.json` on their computer and have them paste the Webhook URL and Webhook key, then save.
5. Set `FORMS_DIR` only if they chose a folder; otherwise keep the default.
6. Run:

```bash
python example-form/server.py
```

7. Open http://127.0.0.1:8765/ for them.

The server rereads `webhook.local.json` on every Submit, so they can save the file without a restart. If they edit it in Notepad on Windows, a hidden byte-order mark may be added; the server reads UTF-8 with BOM, so that still works.

The server listens only on localhost. Nothing is uploaded to a public host.

## webhook.local.json

```json
{
  "url": "https://…",
  "key": "…"
}
```

`.gitignore` already excludes this file.

## Form payload

`POST /submit` with JSON. The example form sends:

```json
{
  "form": "example-form",
  "is_test": true,
  "question": "…",
  "answer": "…",
  "target_bot": "Web Apps"
}
```

`target_bot` must be the exact Grok Bot assistant name that asked for the form. The server adds timestamps and file paths, writes markdown plus JSON, then posts the full record to the webhook.

Suggested webhook routine behavior:

- Read the JSON body.
- Message the Grok Bot assistant named in `target_bot` with the answers and file paths.
- If `target_bot` is missing, tell the person in chat instead of guessing.
- If `target_bot` is the assistant that owns the routine, confirm the submission in that chat.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `FORMS_DIR` | `example-form/submissions` | Where markdown and JSON logs are written |
| `FORM_HOST` | `127.0.0.1` | Bind address (localhost only) |
| `FORM_PORT` | `8765` | Local port |

## Requirements

- Python 3 (standard library only)
- A Grok Bot assistant with a webhook routine
