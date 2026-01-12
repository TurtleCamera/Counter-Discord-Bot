import json
import os
import re
import string
import discord
from discord.ext import commands
from discord import app_commands
from discord import AllowedMentions

# Read token and guild ID
with open("bot.token", "r") as f:
    TOKEN = f.read().strip()
with open("guild.id", "r") as f:
    GUILD_ID = int(f.read().strip())

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

# -------------- Data Paths and Setup --------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

TRACK_FILE = os.path.join(DATA_DIR, "tracked_phrases.json")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")
APPEND_FILE = os.path.join(DATA_DIR, "append_phrases.json")
SHORTCUT_FILE = os.path.join(DATA_DIR, "shortcuts.json")
REPOST_FILE = os.path.join(DATA_DIR, "repost.json")
REPLY_FILE = os.path.join(DATA_DIR, "reply.json")
DELIMITER_FILE = os.path.join(DATA_DIR, "delimiters.json")

# Initialize in-memory reply_data
reply_data = {}

def load_reply():
    global reply_data
    reply_data = load_json(REPLY_FILE)
    return reply_data

def save_reply():
    save_json(REPLY_FILE, reply_data)

# JSON helpers
def load_json(path):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

# Global in-memory data
tracking_data = {}
counters_data = {}
append_data = {}
shortcuts_data = {}
repost_data = {}
delimiters_data = {}

def load_all_data():
    global tracking_data, counters_data, append_data, shortcuts_data, repost_data, reply_data, delimiters_data
    tracking_data = load_json(TRACK_FILE)
    counters_data = load_json(COUNTERS_FILE)
    append_data = load_json(APPEND_FILE)
    shortcuts_data = load_json(SHORTCUT_FILE)
    repost_data = load_json(REPOST_FILE)
    reply_data = load_json(REPLY_FILE)
    delimiters_data = load_json(DELIMITER_FILE)

def save_all_data():
    save_json(TRACK_FILE, tracking_data)
    save_json(COUNTERS_FILE, counters_data)
    save_json(APPEND_FILE, append_data)
    save_json(SHORTCUT_FILE, shortcuts_data)
    save_json(REPOST_FILE, repost_data)
    save_json(REPLY_FILE, reply_data)
    save_json(DELIMITER_FILE, delimiters_data)

# Guild object
guild = discord.Object(id=GUILD_ID)

# -------------- Helper Functions --------------
APOSTROPHES = ["’", "‘", "ʼ", "‛", "＇", "՚", "ߵ", "ߴ"] # Because mobile and PC type different apostrophes
def normalize_apostrophes(text: str) -> str:
    if not text:
        return text
    for char in APOSTROPHES:
        text = text.replace(char, "'")
    return text

# -------------- Webhooks and Messages --------------
# Webhook management
channel_webhooks = {}
WEBHOOK_NAME = "CounterBot Webhook"

async def get_channel_webhook(channel):
    channel_id = str(channel.id)
    webhook = channel_webhooks.get(channel_id)
    if webhook is None:
        webhooks = await channel.webhooks()
        webhook = next((wh for wh in webhooks if wh.name == WEBHOOK_NAME), None)
        if webhook is None:
            webhook = await channel.create_webhook(name=WEBHOOK_NAME)
        channel_webhooks[channel_id] = webhook
    return webhook

# Replace occurrences of the delimiter + display name with real mentions.
def replace_delimiter_mentions(content, guild, delimiter="!"):
    result = []
    i = 0
    n = len(content)

    while i < n:
        if content[i] != delimiter:
            result.append(content[i])
            i += 1
            continue

        matched = False
        # Try every member
        for member in guild.members:
            for name in (member.display_name, member.name):
                name_len = len(name)
                # Check if there's enough characters left
                if i + 1 + name_len > n:
                    continue
                # Case-insensitive exact match
                if content[i+1:i+1+name_len].lower() == name.lower():
                    result.append(member.mention)
                    i += 1 + name_len  # advance past '!' + name
                    matched = True
                    break
            if matched:
                break

        if not matched:
            # No match → keep the delimiter as-is
            result.append(content[i])
            i += 1

    return "".join(result)

# Message handling
@bot.event
async def on_message(message):
    # Ignore messages sent by other bots (including itself) to prevent loops or double processing
    if message.author.bot:
        return

    # If message has attachments but no text, skip because there's nothing to track/append
    if not message.content.strip() and message.attachments:
        await bot.process_commands(message)
        return

    # Skip any message that isn't a default or reply type
    if message.type != discord.MessageType.default and message.type != discord.MessageType.reply:
        return
    
    # Skip empty messages (like forwarded messages, which have no message content)
    if not message.content and not message.attachments:
        return

    # User information
    user_id = str(message.author.id)
    channel_id = str(message.channel.id)
    repost_enabled = repost_data.get(user_id, True)
    user_phrases = tracking_data.get(user_id, [])
    append_phrase = append_data.get(user_id)
    user_shortcuts = shortcuts_data.get(user_id, {})
    modified = normalize_apostrophes(message.content or "") # Handle different cases of apostrophes
    updated = False
    skip_append = False

    # Apply delimiter-based mention replacement to modified message
    user_delimiter = delimiters_data.get(user_id)
    if user_delimiter:
        new_modified = replace_delimiter_mentions(
            modified,
            message.guild,
            delimiter=user_delimiter
        )
        if new_modified != modified:
            modified = new_modified
            updated = True

    # Initialize counters
    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}

    # Helper: Check if phrase at start or end
    def phrase_at_edges(msg, phrase):
        msg = normalize_apostrophes(msg)
        phrase = normalize_apostrophes(phrase)

        msg_clean = re.sub(r' X\d+', '', msg)
        pattern_start = r'^\s*' + re.escape(phrase) + r'(\s|[.!?,;:]|$)'
        pattern_end = r'(\s|[.!?,;:]|^)' + re.escape(phrase) + r'\s*$'

        return (
            re.search(pattern_start, msg_clean, re.IGNORECASE) or
            re.search(pattern_end, msg_clean, re.IGNORECASE)
        )

    # Apply shortcuts
    if modified:
        for shortcut, target_phrase in user_shortcuts.items():
            pattern = r'\b' + re.escape(shortcut) + r'\b'

            def replace_func(match):
                nonlocal skip_append
                replacement = target_phrase
                if target_phrase in user_phrases:
                    if match.end() == len(modified.rstrip('.!?')):
                        skip_append = True
                return replacement

            new_modified = re.sub(pattern, replace_func, modified, flags=re.IGNORECASE)
            if new_modified != modified:
                modified = new_modified
                updated = True

    # Remove existing counters like "phrase X123"
    if modified:
        for phrase in user_phrases:
            # Match cases like "RIP X172" or ":thumbsup: X5"
            norm_phrase = normalize_apostrophes(phrase)
            pattern = rf'(?<!\w)({re.escape(norm_phrase)})\s*X\d+'
            modified = re.sub(pattern, r'\1', modified, flags=re.IGNORECASE)

    # Apply tracked phrase counters
    if modified:
        for phrase in user_phrases:
            norm_phrase = normalize_apostrophes(phrase)
            pattern = r'(?<!\w)(' + re.escape(norm_phrase) + r')(?!\w)'
            matches = list(re.finditer(pattern, modified, flags=re.IGNORECASE))
            if not matches:
                continue
            offset = 0
            for match in matches:
                start, end = match.span()
                start += offset
                end += offset
                current_count = counters_data[user_id][channel_id].get(phrase, 0) + 1
                counters_data[user_id][channel_id][phrase] = current_count
                insert_text = f" X{current_count}"
                modified = modified[:end] + insert_text + modified[end:]
                offset += len(insert_text)
                updated = True

    # Apply append phrase
    if append_phrase and not skip_append:
        content_to_check = modified.strip()
        # Skip if fully enclosed
        if not ((content_to_check.startswith('(') and content_to_check.endswith(')')) or
                (content_to_check.startswith('{') and content_to_check.endswith('}')) or
                (content_to_check.startswith('[') and content_to_check.endswith(']'))):
            # Skip if any tracked phrase is at start or end
            if not any(phrase_at_edges(content_to_check, p) for p in user_phrases):
                if append_phrase in user_phrases:
                    append_count = counters_data[user_id][channel_id].get(append_phrase, 0) + 1
                    counters_data[user_id][channel_id][append_phrase] = append_count
                    append_text = f"{append_phrase} X{append_count}"
                else:
                    append_text = append_phrase

                m = re.search(r'([.!?]+)$', content_to_check)
                if m:
                    punct = m.group(1)
                    core = content_to_check[:-len(punct)]
                else:
                    core = content_to_check
                    punct = ''
                modified = f"{core}, {append_text}{punct}"
                updated = True

    # Delete/repost only if enabled
    if updated:
        save_json(COUNTERS_FILE, counters_data)

        # Gather attachments from current message
        files = [await att.to_file() for att in message.attachments]

        # Check if reply quoting is enabled
        user_reply_enabled = reply_data.get(user_id, False)  # default False
        reply_prefix = ""

        if user_reply_enabled and message.reference and isinstance(message.reference.resolved, discord.Message):
            original = message.reference.resolved
            original_lines = original.content.splitlines()

            # Skip bot-generated quotes to avoid double quoting
            if original_lines and re.match(rf"^> <@!?{original.author.id}>", original_lines[0]):
                clean_lines = [line for line in original_lines if not line.startswith("> ")]
            else:
                clean_lines = original_lines

            if clean_lines:
                # Escape URLs in the quote to prevent embeds
                def escape_links(line):
                    # Wrap any http(s) links in <>
                    return re.sub(r'(https?://\S+)', r'<\1>', line)

                quoted_lines = "\n".join(f"> {escape_links(line)}" for line in clean_lines)
                reply_prefix = f"> {original.author.mention}\n{quoted_lines}\n"

        if repost_enabled:
            try:
                webhook = await get_channel_webhook(message.channel)
                await webhook.send(
                    content=reply_prefix + modified,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    wait=True,
                    files=files
                )

                await message.delete()
            except Exception as e:
                print(f"Failed to repost message from {message.author}: {e}")

    await bot.process_commands(message)
   
# -------------- Commands --------------
# /track
@bot.tree.command(name="track", description="Track a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to track")
async def track(interaction: discord.Interaction, phrase: str):
    user_id = str(interaction.user.id)
    if user_id not in tracking_data:
        tracking_data[user_id] = []
    if phrase.lower() in [p.lower() for p in tracking_data[user_id]]:
        await interaction.response.send_message(f"You are already tracking '{phrase}'!", ephemeral=True)
        return
    tracking_data[user_id].append(phrase)
    save_json(TRACK_FILE, tracking_data)
    await interaction.response.send_message(f"You are now tracking: '{phrase}'", ephemeral=True)
    
# /untrack
@bot.tree.command(name="untrack", description="Stop tracking a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to stop tracking")
async def untrack(interaction: discord.Interaction, phrase: str):
    user_id = str(interaction.user.id)
    if user_id not in tracking_data:
        await interaction.response.send_message("You are not tracking any phrases!", ephemeral=True)
        return
    matched = next((p for p in tracking_data[user_id] if p.lower() == phrase.lower()), None)
    if not matched:
        await interaction.response.send_message(f"You are not tracking '{phrase}'!", ephemeral=True)
        return
    tracking_data[user_id].remove(matched)
    if not tracking_data[user_id]:
        del tracking_data[user_id]
    save_json(TRACK_FILE, tracking_data)
    await interaction.response.send_message(f"You have stopped tracking: '{phrase}'", ephemeral=True)
    
# /set
@bot.tree.command(name="set", description="Set the counter for a tracked phrase", guild=guild)
@app_commands.describe(phrase="The phrase", count="Set counter to this number (≥0)")
async def set_counter(interaction: discord.Interaction, phrase: str, count: int):
    if count < 0:
        await interaction.response.send_message("Counter cannot be negative.", ephemeral=True)
        return
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}
    counters_data[user_id][channel_id][phrase] = count
    save_json(COUNTERS_FILE, counters_data)
    await interaction.response.send_message(f"Counter for '{phrase}' set to {count}.", ephemeral=True)
    
# /append
@bot.tree.command(name="append", description="Append a phrase to your messages", guild=guild)
@app_commands.describe(phrase="Phrase to append (leave empty to remove)")
async def append_command(interaction: discord.Interaction, phrase: str = None):
    user_id = str(interaction.user.id)
    if not phrase or phrase.strip() == "":
        if user_id in append_data:
            del append_data[user_id]
            save_json(APPEND_FILE, append_data)
            await interaction.response.send_message("Removed append phrase.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have an append phrase set.", ephemeral=True)
        return
    append_data[user_id] = phrase
    save_json(APPEND_FILE, append_data)
    await interaction.response.send_message(f"Messages will now append '{phrase}'.", ephemeral=True)
    
# /shortcut_add
@bot.tree.command(name="shortcut_add", description="Add a shortcut for a phrase", guild=guild)
@app_commands.describe(phrase="Phrase to replace with", shortcut="Shortcut trigger word")
async def shortcut_add(interaction: discord.Interaction, phrase: str, shortcut: str):
    user_id = str(interaction.user.id)
    if user_id not in shortcuts_data:
        shortcuts_data[user_id] = {}
    if any(s.lower() == shortcut.lower() for s in shortcuts_data[user_id]):
        await interaction.response.send_message(f"Shortcut '{shortcut}' already exists.", ephemeral=True)
        return
    shortcuts_data[user_id][shortcut] = phrase
    save_json(SHORTCUT_FILE, shortcuts_data)
    await interaction.response.send_message(f"Shortcut '{shortcut}' → '{phrase}' added.", ephemeral=True)
    
# /shortcut_remove
@bot.tree.command(name="shortcut_remove", description="Remove a shortcut for a phrase", guild=guild)
@app_commands.describe(phrase="Phrase whose shortcut to remove")
async def shortcut_remove(interaction: discord.Interaction, phrase: str):
    user_id = str(interaction.user.id)
    if user_id not in shortcuts_data:
        await interaction.response.send_message("You don't have any shortcuts.", ephemeral=True)
        return
    to_remove = [s for s, p in shortcuts_data[user_id].items() if p.lower() == phrase.lower()]
    if not to_remove:
        await interaction.response.send_message(f"No shortcut found for '{phrase}'.", ephemeral=True)
        return
    for s in to_remove:
        del shortcuts_data[user_id][s]
    save_json(SHORTCUT_FILE, shortcuts_data)
    await interaction.response.send_message(f"Removed shortcut(s): {', '.join(to_remove)}", ephemeral=True)

# /delimiter
@bot.tree.command(name="delimiter", description="Set your mention delimiter", guild=guild)
@app_commands.describe(delimiter="Single character to use as mention prefix")
async def set_delimiter(interaction: discord.Interaction, delimiter: str = None):
    user_id = str(interaction.user.id)
    
    # If user provided nothing or only whitespace, disable the delimiter
    if not delimiter or delimiter.strip() == "":
        if user_id in delimiters_data:
            del delimiters_data[user_id]
            save_json(DELIMITER_FILE, delimiters_data)
        await interaction.response.send_message(
            "Your mention delimiter is now disabled.", ephemeral=True
        )
        return

    # Enforce single-character delimiter
    if len(delimiter) != 1:
        await interaction.response.send_message(
            "Delimiter must be a single character.", ephemeral=True
        )
        return

    delimiters_data[user_id] = delimiter
    save_json(DELIMITER_FILE, delimiters_data)
    await interaction.response.send_message(
        f"Your mention delimiter is now set to `{delimiter}`.", ephemeral=True
    )

# /repost
@bot.tree.command(name="repost", description="Toggle message reposting on or off", guild=guild)
@app_commands.describe(toggle="Enable or disable reposting (on/off)")
async def repost_command(interaction: discord.Interaction, toggle: str):
    toggle = toggle.lower()
    if toggle not in ["on", "off"]:
        await interaction.response.send_message("Invalid argument. Use `on` or `off`.", ephemeral=True)
        return
    user_id = str(interaction.user.id)
    repost_data[user_id] = toggle == "on"
    save_json(REPOST_FILE, repost_data)
    status = "enabled" if toggle == "on" else "disabled"
    await interaction.response.send_message(f"Reposting is now {status}.", ephemeral=True)

# /reply
@bot.tree.command(
    name="reply",
    description="Toggle the new reply quoting mechanic on or off",
    guild=guild
)
@app_commands.describe(toggle="Enable or disable reply quoting (on/off)")
async def reply(interaction: discord.Interaction, toggle: str):
    toggle = toggle.lower()
    if toggle not in ["on", "off"]:
        await interaction.response.send_message(
            "Invalid argument. Use `on` or `off`.",
            ephemeral=True
        )
        return

    user_id = str(interaction.user.id)
    reply_data[user_id] = toggle == "on"
    save_reply()

    status = "enabled" if toggle == "on" else "disabled"
    await interaction.response.send_message(
        f"Reply quoting is now {status}.",
        ephemeral=True
    )

# /list
@bot.tree.command(name="list", description="List tracked phrases, counters, shortcuts, and append phrase", guild=guild)
async def list_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    embed = discord.Embed(title=f"{interaction.user.display_name}'s Tracking Info", color=discord.Color.blue())

    # Tracked phrases and counters
    user_phrases = tracking_data.get(user_id, [])
    if user_phrases:
        phrase_lines = [f"`{p}` X{counters_data.get(user_id, {}).get(channel_id, {}).get(p, 0)}" for p in user_phrases]
        embed.add_field(name="Tracked Phrases", value="\n".join(phrase_lines), inline=False)
    else:
        embed.add_field(name="Tracked Phrases", value="You are not tracking any phrases.", inline=False)

    # Shortcuts
    user_shortcuts = shortcuts_data.get(user_id, {})
    if user_shortcuts:
        shortcut_lines = [f"`{s}` → `{t}`" for s, t in user_shortcuts.items()]
        embed.add_field(name="Shortcuts", value="\n".join(shortcut_lines), inline=False)
    else:
        embed.add_field(name="Shortcuts", value="No shortcuts set.", inline=False)

    # Append phrase
    append_phrase = append_data.get(user_id)
    if append_phrase:
        embed.add_field(name="Append Phrase", value=f"`{append_phrase}`", inline=False)
    else:
        embed.add_field(name="Append Phrase", value="No append phrase set.", inline=False)

    # Delimiter info
    user_delimiter = delimiters_data.get(user_id)
    if user_delimiter:
        embed.add_field(name="Mention Delimiter", value=f"`{user_delimiter}`", inline=False)
    else:
        embed.add_field(name="Mention Delimiter", value="None", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# /help
@bot.tree.command(name="help", description="Show all commands", guild=guild)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="CounterBot Commands", color=discord.Color.green())
    embed.add_field(name="/track <phrase>", value="Start tracking a phrase.", inline=False)
    embed.add_field(name="/untrack <phrase>", value="Stop tracking a phrase.", inline=False)
    embed.add_field(name="/set <phrase> <count>", value="Set counter.", inline=False)
    embed.add_field(name="/append <phrase>", value="Append a phrase to your messages.", inline=False)
    embed.add_field(name="/shortcut_add <phrase> <shortcut>", value="Add a shortcut.", inline=False)
    embed.add_field(name="/shortcut_remove <phrase>", value="Remove shortcuts.", inline=False)
    embed.add_field(name="/repost [on/off]", value="Toggle reposting messages.", inline=False)
    embed.add_field(name="/reply [on/off]", value="Toggle the new reply quoting mechanic.", inline=False)
    embed.add_field(name="/list", value="List tracked phrases and shortcuts.", inline=False)
    embed.add_field(name="/delimiter <char>", value="Set your mention delimiter (leave empty to disable).", inline=False)
    embed.set_footer(text="Counters are per-channel. Messages are reposted only if enabled. See README.md for full details.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Bot ready
@bot.event
async def on_ready():
    load_all_data()
    await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user} for guild {GUILD_ID}")

# Start bot
bot.run(TOKEN)
