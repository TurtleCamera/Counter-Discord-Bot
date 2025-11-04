import json
import os
import re
import discord
from discord.ext import commands
from discord import app_commands
from discord import AllowedMentions

# -----------------------------
# Read token and guild ID
# -----------------------------
with open("bot.token", "r") as f:
    TOKEN = f.read().strip()
with open("guild.id", "r") as f:
    GUILD_ID = int(f.read().strip())

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# Data paths and setup
# -----------------------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

TRACK_FILE = os.path.join(DATA_DIR, "tracked_phrases.json")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")
APPEND_FILE = os.path.join(DATA_DIR, "append_phrases.json")
SHORTCUT_FILE = os.path.join(DATA_DIR, "shortcuts.json")
REPOST_FILE = os.path.join(DATA_DIR, "repost.json")

# -----------------------------
# JSON helpers
# -----------------------------
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

# -----------------------------
# Global in-memory data
# -----------------------------
tracking_data = {}
counters_data = {}
append_data = {}
shortcuts_data = {}
repost_data = {}

def load_all_data():
    global tracking_data, counters_data, append_data, shortcuts_data, repost_data
    tracking_data = load_json(TRACK_FILE)
    counters_data = load_json(COUNTERS_FILE)
    append_data = load_json(APPEND_FILE)
    shortcuts_data = load_json(SHORTCUT_FILE)
    repost_data = load_json(REPOST_FILE)

def save_all_data():
    save_json(TRACK_FILE, tracking_data)
    save_json(COUNTERS_FILE, counters_data)
    save_json(APPEND_FILE, append_data)
    save_json(SHORTCUT_FILE, shortcuts_data)
    save_json(REPOST_FILE, repost_data)

# -----------------------------
# Guild object
# -----------------------------
guild = discord.Object(id=GUILD_ID)

# -----------------------------
# Webhook management
# -----------------------------
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

# -----------------------------
# Message handling
# -----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    channel_id = str(message.channel.id)

    repost_enabled = repost_data.get(user_id, True)
    if user_id not in tracking_data:
        await bot.process_commands(message)
        return

    user_phrases = tracking_data[user_id]
    append_phrase = append_data.get(user_id)
    user_shortcuts = shortcuts_data.get(user_id, {})
    modified = message.content or ""
    updated = False
    skip_append = False

    # Initialize counters
    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}

    # -----------------------------
    # Helper: Check if phrase at start or end
    # -----------------------------
    def phrase_at_edges(msg, phrase):
        msg_clean = re.sub(r' X\d+', '', msg)
        pattern_start = r'^\s*' + re.escape(phrase) + r'(\s|[.!?,;:]|$)'
        pattern_end = r'(\s|[.!?,;:]|^)' + re.escape(phrase) + r'\s*$'
        return re.search(pattern_start, msg_clean, re.IGNORECASE) or re.search(pattern_end, msg_clean, re.IGNORECASE)

    # -----------------------------
    # Apply shortcuts
    # -----------------------------
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

    # -----------------------------
    # Apply tracked phrase counters
    # -----------------------------
    if modified:
        for phrase in user_phrases:
            pattern = r'(?<!\w)(' + re.escape(phrase) + r')(?!\w)'
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

    # -----------------------------
    # Apply append phrase
    # -----------------------------
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

    # -----------------------------
    # Delete/repost only if enabled
    # -----------------------------
    if updated or message.attachments:
        if updated:
            save_json(COUNTERS_FILE, counters_data)
        files = [await att.to_file() for att in message.attachments]
        if repost_enabled:
            await message.delete()
            webhook = await get_channel_webhook(message.channel)
            await webhook.send(
                content=modified if updated else None,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                wait=True,
                files=files,
                allowed_mentions=AllowedMentions.none()
            )

    await bot.process_commands(message)

# -----------------------------
# Slash commands
# -----------------------------
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
    await interaction.response.send_message(f"✅ You are now tracking: '{phrase}'", ephemeral=True)

@bot.tree.command(name="untrack", description="Stop tracking a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to stop tracking")
async def untrack(interaction: discord.Interaction, phrase: str):
    user_id = str(interaction.user.id)
    if user_id not in tracking_data:
        await interaction.response.send_message("❌ You are not tracking any phrases!", ephemeral=True)
        return
    matched = next((p for p in tracking_data[user_id] if p.lower() == phrase.lower()), None)
    if not matched:
        await interaction.response.send_message(f"❌ You are not tracking '{phrase}'!", ephemeral=True)
        return
    tracking_data[user_id].remove(matched)
    if not tracking_data[user_id]:
        del tracking_data[user_id]
    save_json(TRACK_FILE, tracking_data)
    await interaction.response.send_message(f"✅ You have stopped tracking: '{phrase}'", ephemeral=True)

@bot.tree.command(name="set", description="Set the counter for a tracked phrase", guild=guild)
@app_commands.describe(phrase="The phrase", count="Set counter to this number (≥0)")
async def set_counter(interaction: discord.Interaction, phrase: str, count: int):
    if count < 0:
        await interaction.response.send_message("❌ Counter cannot be negative.", ephemeral=True)
        return
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}
    counters_data[user_id][channel_id][phrase] = count
    save_json(COUNTERS_FILE, counters_data)
    await interaction.response.send_message(f"✅ Counter for '{phrase}' set to {count}.", ephemeral=True)

@bot.tree.command(name="append", description="Append a phrase to your messages", guild=guild)
@app_commands.describe(phrase="Phrase to append (leave empty to remove)")
async def append_command(interaction: discord.Interaction, phrase: str = None):
    user_id = str(interaction.user.id)
    if not phrase or phrase.strip() == "":
        if user_id in append_data:
            del append_data[user_id]
            save_json(APPEND_FILE, append_data)
            await interaction.response.send_message("✅ Removed append phrase.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You don't have an append phrase set.", ephemeral=True)
        return
    append_data[user_id] = phrase
    save_json(APPEND_FILE, append_data)
    await interaction.response.send_message(f"✅ Messages will now append '{phrase}'.", ephemeral=True)

@bot.tree.command(name="shortcut_add", description="Add a shortcut for a phrase", guild=guild)
@app_commands.describe(phrase="Phrase to replace with", shortcut="Shortcut trigger word")
async def shortcut_add(interaction: discord.Interaction, phrase: str, shortcut: str):
    user_id = str(interaction.user.id)
    if user_id not in shortcuts_data:
        shortcuts_data[user_id] = {}
    if any(s.lower() == shortcut.lower() for s in shortcuts_data[user_id]):
        await interaction.response.send_message(f"❌ Shortcut '{shortcut}' already exists.", ephemeral=True)
        return
    shortcuts_data[user_id][shortcut] = phrase
    save_json(SHORTCUT_FILE, shortcuts_data)
    await interaction.response.send_message(f"✅ Shortcut '{shortcut}' → '{phrase}' added.", ephemeral=True)

@bot.tree.command(name="shortcut_remove", description="Remove a shortcut for a phrase", guild=guild)
@app_commands.describe(phrase="Phrase whose shortcut to remove")
async def shortcut_remove(interaction: discord.Interaction, phrase: str):
    user_id = str(interaction.user.id)
    if user_id not in shortcuts_data:
        await interaction.response.send_message("❌ You don't have any shortcuts.", ephemeral=True)
        return
    to_remove = [s for s, p in shortcuts_data[user_id].items() if p.lower() == phrase.lower()]
    if not to_remove:
        await interaction.response.send_message(f"❌ No shortcut found for '{phrase}'.", ephemeral=True)
        return
    for s in to_remove:
        del shortcuts_data[user_id][s]
    save_json(SHORTCUT_FILE, shortcuts_data)
    await interaction.response.send_message(f"✅ Removed shortcut(s): {', '.join(to_remove)}", ephemeral=True)

@bot.tree.command(name="repost", description="Toggle message reposting on or off", guild=guild)
@app_commands.describe(toggle="Enable or disable reposting (on/off)")
async def repost_command(interaction: discord.Interaction, toggle: str):
    toggle = toggle.lower()
    if toggle not in ["on", "off"]:
        await interaction.response.send_message("❌ Invalid argument. Use `on` or `off`.", ephemeral=True)
        return
    user_id = str(interaction.user.id)
    repost_data[user_id] = toggle == "on"
    save_json(REPOST_FILE, repost_data)
    status = "enabled" if toggle == "on" else "disabled"
    await interaction.response.send_message(f"✅ Reposting is now {status}.", ephemeral=True)

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

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="Show all commands", guild=guild)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 CounterBot Commands", color=discord.Color.green())
    embed.add_field(name="/track <phrase>", value="Start tracking a phrase.", inline=False)
    embed.add_field(name="/untrack <phrase>", value="Stop tracking a phrase.", inline=False)
    embed.add_field(name="/set <phrase> <count>", value="Set counter.", inline=False)
    embed.add_field(name="/append <phrase>", value="Append a phrase to your messages.", inline=False)
    embed.add_field(name="/shortcut_add <phrase> <shortcut>", value="Add a shortcut.", inline=False)
    embed.add_field(name="/shortcut_remove <phrase>", value="Remove shortcuts.", inline=False)
    embed.add_field(name="/repost [on/off]", value="Toggle reposting messages.", inline=False)
    embed.add_field(name="/list", value="List tracked phrases and shortcuts.", inline=False)
    embed.set_footer(text="Counters are per-channel. Messages are reposted only if enabled.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -----------------------------
# Bot ready
# -----------------------------
@bot.event
async def on_ready():
    load_all_data()
    await bot.tree.sync(guild=guild)
    print(f"✅ Logged in as {bot.user} for guild {GUILD_ID}")

# -----------------------------
# Start bot
# -----------------------------
bot.run(TOKEN)
