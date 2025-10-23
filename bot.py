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
os.makedirs(DATA_DIR, exist_ok=True)  # Create directory if it doesn't exist

# Paths to JSON files inside the data directory
TRACK_FILE = os.path.join(DATA_DIR, "tracked_phrases.json")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")
APPEND_FILE = os.path.join(DATA_DIR, "append_phrases.json")
SHORTCUT_FILE = os.path.join(DATA_DIR, "shortcuts.json")

# -----------------------------
# Helper functions for tracking
# -----------------------------
def load_tracking():
    if not os.path.exists(TRACK_FILE):
        with open(TRACK_FILE, "w") as f:
            json.dump({}, f)
        return {}
    with open(TRACK_FILE, "r") as f:
        return json.load(f)

def save_tracking(data):
    with open(TRACK_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------
# Helper functions for counters
# -----------------------------
def load_counters():
    if not os.path.exists(COUNTERS_FILE):
        with open(COUNTERS_FILE, "w") as f:
            json.dump({}, f)
        return {}
    with open(COUNTERS_FILE, "r") as f:
        return json.load(f)

def save_counters(data):
    with open(COUNTERS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------
# Helper functions for append
# -----------------------------
def load_append():
    if not os.path.exists(APPEND_FILE):
        with open(APPEND_FILE, "w") as f:
            json.dump({}, f)
        return {}
    with open(APPEND_FILE, "r") as f:
        return json.load(f)

def save_append(data):
    with open(APPEND_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------
# Helper functions for shortcuts
# -----------------------------
def load_shortcuts():
    if not os.path.exists(SHORTCUT_FILE):
        with open(SHORTCUT_FILE, "w") as f:
            json.dump({}, f)
        return {}
    with open(SHORTCUT_FILE, "r") as f:
        return json.load(f)

def save_shortcuts(data):
    with open(SHORTCUT_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------
# Guild object for slash commands
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
# Message-delete and repost logic
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

    if user_id not in tracking_data:
        await bot.process_commands(message)
        return

    user_phrases = tracking_data[user_id]
    append_phrase = append_data.get(user_id, None)
    user_shortcuts = shortcuts_data.get(user_id, {})
    modified = message.content or ""
    updated = False
    skip_append = False  # Prevent append if a shortcut replaced a tracked phrase at the end

    # -----------------------------
    # Initialize counters if needed
    # -----------------------------
    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}

    # -----------------------------
    # Apply shortcuts
    # -----------------------------
    if modified:
        for shortcut, target_phrase in user_shortcuts.items():
            pattern = r'\b' + re.escape(shortcut) + r'\b'

            def replace_func(match):
                nonlocal skip_append
                replacement = target_phrase
                # If the target phrase is tracked and appears at the end (ignoring punctuation),
                # skip appending the append phrase
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
            phrase_lower = phrase.lower()
            start = 0
            content_lower = modified.lower()
            while True:
                index = content_lower.find(phrase_lower, start)
                if index == -1:
                    break

                # Increment counter for this phrase in this channel
                current_count = counters_data[user_id][channel_id].get(phrase, 0) + 1
                counters_data[user_id][channel_id][phrase] = current_count

                before = modified[:index + len(phrase)]
                after = modified[index + len(phrase):]
                modified = before + f" X{current_count}" + after

                start = index + len(phrase) + len(f" X{current_count}")
                updated = True
                content_lower = modified.lower()

    # -----------------------------
    # Apply append phrase
    # -----------------------------
    if append_phrase and not skip_append:
        content_to_check = modified.strip()

        # Skip appending if the message is fully enclosed in (), {}, or []
        if not ((content_to_check.startswith('(') and content_to_check.endswith(')')) or
                (content_to_check.startswith('{') and content_to_check.endswith('}')) or
                (content_to_check.startswith('[') and content_to_check.endswith(']'))):

            # Skip if the message starts or ends with a tracked phrase
            if not any(content_to_check.lower().startswith(p.lower()) or content_to_check.lower().endswith(p.lower())
                       for p in user_phrases):

                # Only add a counter if the append phrase is tracked
                if append_phrase in user_phrases:
                    append_count = counters_data[user_id][channel_id].get(append_phrase, 0) + 1
                    counters_data[user_id][channel_id][append_phrase] = append_count
                    append_text = f"{append_phrase} X{append_count}"
                else:
                    append_text = append_phrase

                # Preserve sentence-ending punctuation
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
    # Delete original message and repost
    # -----------------------------
    if updated or message.attachments:
        if updated:
            save_counters(counters_data)
        files = [await att.to_file() for att in message.attachments]
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
        await interaction.response.send_message(f"❌ You are not tracking any phrases!", ephemeral=True)
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
    await interaction.response.send_message(
        f"✅ Counter for '{matched_phrase}' in this channel has been set to {count}.",
        ephemeral=True
    )

# -----------------------------
# Slash command: /append
# -----------------------------
@bot.tree.command(
    name="append",
    description="Append a phrase to the end of your messages",
    guild=guild
)
@app_commands.describe(
    phrase="A phrase to append to messages (leave empty to remove)"
)
async def append_command(interaction: discord.Interaction, phrase: str = None):
    user_id = str(interaction.user.id)
    append_data = load_append()

    if phrase is None or phrase.strip() == "":
        # Remove currently set append phrase
        if user_id in append_data:
            del append_data[user_id]
            save_append(append_data)
            await interaction.response.send_message(
                "✅ Removed the append phrase from your messages.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ You don't have an append phrase set.",
                ephemeral=True
            )
        return

    # Set the append phrase without checking if it's tracked
    append_data[user_id] = phrase
    save_append(append_data)
    await interaction.response.send_message(
        f"✅ Messages you send will now have '{phrase}' appended to the end of the message.",
        ephemeral=True
    )

# -----------------------------
# /shortcut_add
# -----------------------------
@bot.tree.command(name="shortcut_add", description="Add a shortcut for a phrase", guild=guild)
@app_commands.describe(
    phrase="The phrase to replace with",
    shortcut="The shortcut word to trigger replacement"
)
async def shortcut_add(interaction: discord.Interaction, phrase: str, shortcut: str):
    user_id = str(interaction.user.id)
    shortcuts_data = load_shortcuts()
    if user_id not in shortcuts_data:
        shortcuts_data[user_id] = {}

    # Case-insensitive check for duplicate shortcut
    if any(s.lower() == shortcut.lower() for s in shortcuts_data[user_id].keys()):
        await interaction.response.send_message(f"❌ You already have a shortcut '{shortcut}'.", ephemeral=True)
        return

    shortcuts_data[user_id][shortcut] = phrase
    save_shortcuts(shortcuts_data)
    await interaction.response.send_message(
        f"✅ Shortcut '{shortcut}' added for phrase '{phrase}'.",
        ephemeral=True
    )

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

    # Case-insensitive match for target phrase
    to_remove = [s for s, p in shortcuts_data[user_id].items() if p.lower() == phrase.lower()]
    if not to_remove:
        await interaction.response.send_message(f"❌ No shortcut found for phrase '{phrase}'.", ephemeral=True)
        return

    for s in to_remove:
        del shortcuts_data[user_id][s]
    save_shortcuts(shortcuts_data)
    await interaction.response.send_message(
        f"✅ Removed shortcut(s) for phrase '{phrase}': {', '.join(to_remove)}",
        ephemeral=True
    )

# -----------------------------
# Slash command: /list
# -----------------------------
@bot.tree.command(
    name="list",
    description="List all tracked phrases, their counters, and shortcuts in this channel",
    guild=guild
)
async def list_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)

    tracking_data = load_tracking()
    counters_data = load_counters()
    shortcuts_data = load_shortcuts()

    embed = discord.Embed(
        title=f"{interaction.user.display_name}'s Tracking Information",
        color=discord.Color.blue()
    )

    # -----------------------------
    # Tracked phrases with counters
    # -----------------------------
    user_phrases = tracking_data.get(user_id, [])
    if user_phrases:
        phrase_lines = []
        for phrase in user_phrases:
            count = counters_data.get(user_id, {}).get(channel_id, {}).get(phrase, 0)
            phrase_lines.append(f"`{phrase}` — X{count}")
        embed.add_field(
            name="Tracked Phrases",
            value="\n".join(phrase_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="Tracked Phrases",
            value="You are not tracking any phrases.",
            inline=False
        )

    # -----------------------------
    # Shortcuts
    # -----------------------------
    user_shortcuts = shortcuts_data.get(user_id, {})
    if user_shortcuts:
        shortcut_lines = []
        for shortcut, target in user_shortcuts.items():
            shortcut_lines.append(f"`{shortcut}` → `{target}`")
        embed.add_field(
            name="Shortcuts",
            value="\n".join(shortcut_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="Shortcuts",
            value="You have no shortcuts set.",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# -----------------------------
# Slash command: /help
# -----------------------------
@bot.tree.command(
    name="help",
    description="Show a list of all available commands and what they do",
    guild=guild
)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 CounterBot Commands",
        description="Here's a summary of all the commands you can use:",
        color=discord.Color.green()
    )

    embed.add_field(
        name="/track <phrase>",
        value="Start tracking a phrase. Counts will be appended to it when you send messages containing it.",
        inline=False
    )

    embed.add_field(
        name="/untrack <phrase>",
        value="Stop tracking a phrase.",
        inline=False
    )

    embed.add_field(
        name="/set <phrase> <count>",
        value="Set the counter for a tracked phrase in the current channel.",
        inline=False
    )

    embed.add_field(
        name="/append [phrase]",
        value="Append a phrase to the end of your messages. Leave the argument empty to remove the append phrase.",
        inline=False
    )

    embed.add_field(
        name="/shortcut_add <phrase> <shortcut>",
        value="Create a shortcut so typing <shortcut> will replace it with <phrase> in your messages.",
        inline=False
    )

    embed.add_field(
        name="/shortcut_remove <phrase>",
        value="Remove all shortcuts associated with a phrase.",
        inline=False
    )

    embed.add_field(
        name="/list",
        value="List all your tracked phrases and their counters in this channel, as well as your shortcuts.",
        inline=False
    )

    embed.set_footer(text="All counters are per-channel. Messages are reposted to include counters if needed.")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# -----------------------------
# Bot ready
# -----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=guild)
    print(f"✅ Logged in as {bot.user} for guild {GUILD_ID}")

# -----------------------------
# Start the bot
# -----------------------------
bot.run(TOKEN)
