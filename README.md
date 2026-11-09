# grokbot-local-forms

Local HTML forms for [Grok Bot](https://grok.com) that save answers on your computer and notify the requesting bot when you hit Submit.

This is a small template you can copy. Forms stay private on your machine. Submit is the only action you take: answers are written as markdown and JSON, then a webhook wakes the Grok Bot assistant named in the form.

## The one step you have to do yourself

Almost everything else is automatic. The form can open on your computer, Submit saves your answers, and the requesting Grok Bot gets pinged.

Grok Bot hides the webhook key from assistants on purpose, so the bot cannot fill this in for you.

Once, you (or your assistant) open `webhook.local.json` on your computer. If that file does not exist yet, copy it from `webhook.local.json.example`.

In Grok Bot, open your webhook routine and copy the **Webhook URL** and **Webhook key** into that file. You do not need the Authorization header. The server already sends `Authorization: Bearer` plus the key.

Do not paste the key into chat. Do not commit `webhook.local.json`.

After you save that file, every later Submit is automatic. You do not repeat this for each form.

## How it works

1. A tiny server on your computer hosts the form at `http://127.0.0.1:8765/`.
2. When you click Submit, the server saves a markdown note and a JSON record to a folder you choose (an Obsidian vault folder works well).
3. The same Submit request posts that record to a Grok Bot webhook routine.
4. The routine messages the assistant named in `target_bot` so they can continue without you going back to tell them the form is in.

Nothing is uploaded to a public host. The server listens only on localhost.

## One-time setup

1. Clone this repository.
2. Copy `webhook.local.json.example` to `webhook.local.json` in the repository root.
3. In Grok Bot, create a webhook routine (a name like “Form submission handoff” is fine).
4. Copy the routine’s **Webhook URL** and **Webhook key** into `webhook.local.json`. Do not paste the key into chat, and do not commit this file.
5. Set `FORMS_DIR` to the folder where submissions should be saved, or accept the default `submissions/` directory next to the example form.
6. Start the example form:

```bash
python example-form/server.py
```

7. Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/) in your browser.

After that, every Submit uses the same URL and key. You do not repeat the webhook setup for each form.

If you edit `webhook.local.json` in Notepad on Windows, it may save a hidden byte-order mark at the start of the file. The server reads the file as UTF-8 with BOM, so that will not break the ping.

## webhook.local.json

```json
{
  "url": "https://…",
  "key": "…"
}
```

The server sends `Authorization: Bearer <key>` and `Content-Type: application/json`. You do not need to store the header separately.

Keep `webhook.local.json` out of git. `.gitignore` already lists it.

## Form payload

`POST /submit` with a JSON body. The example form sends:

```json
{
  "form": "example-form",
  "is_test": true,
  "question": "…",
  "answer": "…",
  "target_bot": "Web Apps"
}
```

`target_bot` should be the exact Grok Bot assistant name that asked for the form. The server adds timestamps and the saved file paths, writes markdown plus JSON, then posts the full record to the webhook.

Suggested webhook routine behavior:

- Read the JSON body.
- Message the Grok Bot assistant named in `target_bot` with the answers and file paths.
- If `target_bot` is missing, tell the user in chat instead of guessing.
- If `target_bot` is the bot that owns the routine, just confirm the submission in that chat.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `FORMS_DIR` | `example-form/submissions` | Where markdown and JSON logs are written |
| `FORM_HOST` | `127.0.0.1` | Bind address (localhost only by default) |
| `FORM_PORT` | `8765` | Local port |

The webhook file is read from `webhook.local.json` in the repository root on every Submit, so you can fill it in without restarting the server.

## Make your own form

Copy `example-form/` and change the questions, the `form` id, and `target_bot`. Keep posting JSON to `/submit`. Point each real interview form at the assistant that requested it, not at a generic name.

## Requirements

- Python 3 (standard library only)
- A Grok Bot assistant with a webhook routine
