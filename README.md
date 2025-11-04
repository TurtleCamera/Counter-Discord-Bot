# Counter Discord Bot

A Discord bot that allows users to track counters for various phrases (such as 👍, RIP, etc.) and automate using these phrases and counters in channels.

---

## Commands

> **Command syntax:**
> - All **base commands** are **slash commands** (e.g., `/track`).
> - Everything in `[ ]` is a **literal**.
> - Everything in `< >` is a **non-literal argument** (something you provide, like a phrase or number).

---

### `/help`
Displays the list of available commands and their descriptions.

---

### `/track <phrase>`
Starts counting the number of times a phrase is used in messages per channel.
- Counts are automatically appended when the phrase is used in messages.

---

### `/untrack <phrase>`
Stops counting the specified phrase.

---

### `/list`
Lists all your currently tracked phrases, their counters in the current channel, and shortcuts.

---

### `/set <phrase> <count>`
Sets the counter of a phrase to the specified value for the current channel.
- The phrase must be **tracked**.
- The count must be **≥ 0**.

---

### `/append <phrase>`
Appends a phrase to the end of your messages.
- Running the command without arguments **removes** the append phrase.
- The append is **cancelled** if:
    - A tracked phrase is already at the start or end of the message (including shortcuts that turn into tracked phrases).
    - The message is fully enclosed in `()`, `[]`, or `{}`.

---

### `/shortcut_add <phrase> <shortcut>`
Adds a shortcut for a phrase.
- Typing the shortcut in a message replaces it with the corresponding phrase.

---

### `/shortcut_remove <phrase>`
Removes all shortcuts associated with a phrase.

---

### `/repost [on/off]`
Toggles the reposting feature.
- When **on**, messages containing tracked phrases are deleted and reposted with counters, appended phrases, and shortcuts applied.  
  - Reposts that contain mentions do not trigger a second ping.
  - If the message is a reply, the bot will include a quoted preview of the original message with the user mentioned.  
  - Attachments are preserved and reposted along with the message.  
  - System messages (like pins, joins, boosts) are **not** reposted.
- When **off**, counters are still incremented, but messages are not reposted.

---

### `/reply [on/off]`

Toggles the new reply quoting mechanic.

* When **on**, replies to messages will include a quoted preview of the original message with the user mentioned, even when messages are reposted.
* When **off**, replies are reposted normally without quoting the original message.
* Attachments in the original message are included in the reply.

---

## Example Usage
```plaintext
/track :thumbsup:
/track RIP
/set :thumbsup: 10
/append :thumbsup:
/shortcut_add :thumbsup: tu
/repost off
/list
/help
