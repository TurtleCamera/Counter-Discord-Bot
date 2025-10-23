import json
import os
import re
import discord
from discord.ext import commands
from discord import app_commands

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

# Directory for all JSON files
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Paths to JSON files
TRACK_FILE = os.path.join(DATA_DIR, "tracked_phrases.json")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")
APPEND_FILE = os.path.join(DATA_DIR, "append_phrases.json")
SHORTCUT_FILE = os.path.join(DATA_DIR, "shortcuts.json")
REPOST_FILE = os.path.join(DATA_DIR, "repost.json")  # For repost toggle

# -----------------------------
# Helper functions
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

def load_tracking(): return load_json(TRACK_FILE)
def save_tracking(data): save_json(TRACK_FILE, data)

def load_counters(): return load_json(COUNTERS_FILE)
def save_counters(data): save_json(COUNTERS_FILE, data)

def load_append(): return load_json(APPEND_FILE)
def save_append(data): save_json(APPEND_FILE, data)

def load_shortcuts(): return load_json(SHORTCUT_FILE)
def save_shortcuts(data): save_json(SHORTCUT_FILE, data)

def load_repost(): return load_json(REPOST_FILE)
def save_repost(data): save_json(REPOST_FILE, data)

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

    tracking_data = load_tracking()
    counters_data = load_counters()
    append_data = load_append()
    shortcuts_data = load_shortcuts()
    repost_data = load_repost()

    repost_enabled = repost_data.get(user_id, True)  # default to True

    if user_id not in tracking_data:
        await bot.process_commands(message)
        return

    user_phrases = tracking_data[user_id]
    append_phrase = append_data.get(user_id, None)
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
    # Helper: Check if a phrase is at start or end
    # -----------------------------
    def phrase_at_edges(msg, phrase):
        # Start of message
        pattern_start = r'^\s*' + re.escape(phrase) + r'(\s|[.!?,;:]|$)'
        # End of message
        pattern_end = r'(\s|[.!?,;:]|^)' + re.escape(phrase) + r'\s*$'
        return re.search(pattern_start, msg, re.IGNORECASE) or re.search(pattern_end, msg, re.IGNORECASE)

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
    # Apply tracked phrase counters (whole words / punctuation)
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
            # Skip if any tracked phrase is at the start or end
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
            save_counters(counters_data)
        files = [await att.to_file() for att in message.attachments]
        if repost_enabled:
            await message.delete()
            webhook = await get_channel_webhook(message.channel)
            await webhook.send(
                content=modified if updated else None,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                wait=True,
                files=files
            )

    await bot.process_commands(message)

# -----------------------------
# /track
# -----------------------------
@bot.tree.command(name="track", description="Track a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to track")
async def track(interaction: discord.Interaction, phrase: str):
    data = load_tracking()
    user_id = str(interaction.user.id)
    if user_id not in data:
        data[user_id] = []

    if phrase.lower() in [p.lower() for p in data[user_id]]:
        await interaction.response.send_message(f"You are already tracking '{phrase}'!", ephemeral=True)
        return

    data[user_id].append(phrase)
    save_tracking(data)
    await interaction.response.send_message(f"✅ You are now tracking: '{phrase}'", ephemeral=True)

# -----------------------------
# /untrack
# -----------------------------
@bot.tree.command(name="untrack", description="Stop tracking a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to stop tracking")
async def untrack(interaction: discord.Interaction, phrase: str):
    data = load_tracking()
    user_id = str(interaction.user.id)
    if user_id not in data:
        await interaction.response.send_message("❌ You are not tracking any phrases!", ephemeral=True)
        return
    matched_phrase = next((p for p in data[user_id] if p.lower() == phrase.lower()), None)
    if not matched_phrase:
        await interaction.response.send_message(f"❌ You are not tracking '{phrase}'!", ephemeral=True)
        return
    data[user_id].remove(matched_phrase)
    if not data[user_id]:
        del data[user_id]
    save_tracking(data)
    await interaction.response.send_message(f"✅ You have stopped tracking: '{phrase}'", ephemeral=True)

# -----------------------------
# /set
# -----------------------------
@bot.tree.command(name="set", description="Set the counter for a tracked phrase", guild=guild)
@app_commands.describe(
    phrase="The phrase whose counter you want to set",
    count="The number to set the counter to (0 resets the counter so the next message starts at 1)"
)
async def set_counter(interaction: discord.Interaction, phrase: str, count: int):
    if count < 0:
        await interaction.response.send_message("❌ Counter cannot be negative.", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    counters_data = load_counters()

    # Case-insensitive match for phrase key
    matched_phrase = next((p for p in counters_data.get(user_id, {}).get(channel_id, {}) if p.lower() == phrase.lower()), phrase)

    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}

    counters_data[user_id][channel_id][matched_phrase] = count
    save_counters(counters_data)
    await interaction.response.send_message(f"✅ Counter for '{matched_phrase}' in this channel has been set to {count}.", ephemeral=True)

# -----------------------------
# /append
# -----------------------------
@bot.tree.command(name="append", description="Append a phrase to the end of your messages", guild=guild)
@app_commands.describe(phrase="A phrase to append to messages (leave empty to remove)")
async def append_command(interaction: discord.Interaction, phrase: str = None):
    user_id = str(interaction.user.id)
    append_data = load_append()
    if phrase is None or phrase.strip() == "":
        if user_id in append_data:
            del append_data[user_id]
            save_append(append_data)
            await interaction.response.send_message("✅ Removed the append phrase from your messages.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You don't have an append phrase set.", ephemeral=True)
        return
    append_data[user_id] = phrase
    save_append(append_data)
    await interaction.response.send_message(f"✅ Messages you send will now have '{phrase}' appended.", ephemeral=True)

# -----------------------------
# /shortcut_add
# -----------------------------
@bot.tree.command(name="shortcut_add", description="Add a shortcut for a phrase", guild=guild)
@app_commands.describe(phrase="The phrase to replace with", shortcut="The shortcut word to trigger replacement")
async def shortcut_add(interaction: discord.Interaction, phrase: str, shortcut: str):
    user_id = str(interaction.user.id)
    shortcuts_data = load_shortcuts()
    if user_id not in shortcuts_data:
        shortcuts_data[user_id] = {}

    if any(s.lower() == shortcut.lower() for s in shortcuts_data[user_id]):
        await interaction.response.send_message(f"❌ You already have a shortcut '{shortcut}'.", ephemeral=True)
        return

    shortcuts_data[user_id][shortcut] = phrase
    save_shortcuts(shortcuts_data)
    await interaction.response.send_message(f"✅ Shortcut '{shortcut}' added for phrase '{phrase}'.", ephemeral=True)

# -----------------------------
# /shortcut_remove
# -----------------------------
@bot.tree.command(name="shortcut_remove", description="Remove a shortcut for a phrase", guild=guild)
@app_commands.describe(phrase="The phrase whose shortcut you want to remove")
async def shortcut_remove(interaction: discord.Interaction, phrase: str):
    user_id = str(interaction.user.id)
    shortcuts_data = load_shortcuts()
    if user_id not in shortcuts_data:
        await interaction.response.send_message("❌ You don't have any shortcuts.", ephemeral=True)
        return

    to_remove = [s for s, p in shortcuts_data[user_id].items() if p.lower() == phrase.lower()]
    if not to_remove:
        await interaction.response.send_message(f"❌ No shortcut found for phrase '{phrase}'.", ephemeral=True)
        return

    for s in to_remove:
        del shortcuts_data[user_id][s]
    save_shortcuts(shortcuts_data)
    await interaction.response.send_message(f"✅ Removed shortcut(s) for phrase '{phrase}': {', '.join(to_remove)}", ephemeral=True)

# -----------------------------
# /repost toggle
# -----------------------------
@bot.tree.command(name="repost", description="Toggle message reposting on or off", guild=guild)
@app_commands.describe(toggle="Enable or disable reposting (on/off)")
async def repost_command(interaction: discord.Interaction, toggle: str):
    toggle = toggle.lower()
    if toggle not in ["on", "off"]:
        await interaction.response.send_message("❌ Invalid argument. Use `on` or `off`.", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    repost_data = load_repost()
    repost_data[user_id] = toggle == "on"
    save_repost(repost_data)
    status = "enabled" if toggle == "on" else "disabled"
    await interaction.response.send_message(f"✅ Reposting is now {status}.", ephemeral=True)

# -----------------------------
# /list
# -----------------------------
@bot.tree.command(name="list", description="List all tracked phrases, counters, and shortcuts in this channel", guild=guild)
async def list_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    tracking_data = load_tracking()
    counters_data = load_counters()
    shortcuts_data = load_shortcuts()
    embed = discord.Embed(title=f"{interaction.user.display_name}'s Tracking Info", color=discord.Color.blue())

    user_phrases = tracking_data.get(user_id, [])
    if user_phrases:
        phrase_lines = [f"`{p}` X{counters_data.get(user_id, {}).get(channel_id, {}).get(p,0)}" for p in user_phrases]
        embed.add_field(name="Tracked Phrases", value="\n".join(phrase_lines), inline=False)
    else:
        embed.add_field(name="Tracked Phrases", value="You are not tracking any phrases.", inline=False)

    user_shortcuts = shortcuts_data.get(user_id, {})
    if user_shortcuts:
        shortcut_lines = [f"`{s}` → `{t}`" for s, t in user_shortcuts.items()]
        embed.add_field(name="Shortcuts", value="\n".join(shortcut_lines), inline=False)
    else:
        embed.add_field(name="Shortcuts", value="No shortcuts set.", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# -----------------------------
# /help
# -----------------------------
@bot.tree.command(name="help", description="Show all commands", guild=guild)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 CounterBot Commands", description="Commands you can use:", color=discord.Color.green())
    embed.add_field(name="/track <phrase>", value="Start tracking a phrase.", inline=False)
    embed.add_field(name="/untrack <phrase>", value="Stop tracking a phrase.", inline=False)
    embed.add_field(name="/set <phrase> <count>", value="Set counter in this channel.", inline=False)
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
    await bot.tree.sync(guild=guild)
    print(f"✅ Logged in as {bot.user} for guild {GUILD_ID}")

# -----------------------------
# Start bot
# -----------------------------
bot.run(TOKEN)
