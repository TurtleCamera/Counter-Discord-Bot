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

# Paths to JSON files
TRACK_FILE = "tracked_phrases.json"
COUNTERS_FILE = "counters.json"
APPEND_FILE = "append_phrases.json"

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
# Message-delete and repost logic with counters and append
# -----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return  # ignore bot messages

    user_id = str(message.author.id)
    channel_id = str(message.channel.id)
    tracking_data = load_tracking()
    counters_data = load_counters()
    append_data = load_append()  # Load append info

    if user_id not in tracking_data:
        await bot.process_commands(message)
        return  # user tracks nothing, do nothing

    user_phrases = tracking_data[user_id]
    append_phrase = append_data.get(user_id, None)  # Get user's append phrase
    content_lower = message.content.lower() if message.content else ""
    modified = message.content or ""  # will hold the modified message
    updated = False

    # Initialize counters structure
    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}

    # Process each phrase left-to-right only if there is text
    if modified:
        for phrase in user_phrases:
            phrase_lower = phrase.lower()
            start = 0
            while True:
                index = content_lower.find(phrase_lower, start)
                if index == -1:
                    break
                # Get current counter and increment first
                current_count = counters_data[user_id][channel_id].get(phrase, 0) + 1
                counters_data[user_id][channel_id][phrase] = current_count

                # Append " X{current_count}" after the phrase in the original message
                before = modified[:index + len(phrase)]
                after = modified[index + len(phrase):]
                modified = before + f" X{current_count}" + after

                # Move start index past this occurrence (including appended counter)
                start = index + len(phrase) + len(f" X{current_count}")
                updated = True

                # Update content_lower for case-insensitive search
                content_lower = modified.lower()

    # -----------------------------
    # Apply /append phrase per sentence (with counter)
    # -----------------------------
    if append_phrase:
        # Initialize counter for append_phrase
        append_count = counters_data[user_id][channel_id].get(append_phrase, 0)

        content_to_check = modified.strip()
        content_lower = content_to_check.lower()

        # Skip if the whole message is enclosed by (), {}, or []
        if (content_to_check.startswith('(') and content_to_check.endswith(')')) or \
        (content_to_check.startswith('{') and content_to_check.endswith('}')) or \
        (content_to_check.startswith('[') and content_to_check.endswith(']')):
            pass  # do not append
        else:
            # Skip if message starts or ends with a tracked phrase
            if not any(content_lower.startswith(p.lower()) or content_lower.endswith(p.lower()) for p in user_phrases):
                # Increment counter
                append_count += 1
                counters_data[user_id][channel_id][append_phrase] = append_count

                # Extract trailing punctuation (if any)
                m = re.search(r'([.!?]+)$', content_to_check)
                if m:
                    punct = m.group(1)
                    core = content_to_check[:-len(punct)]
                else:
                    punct = ''
                    core = content_to_check

                # Append phrase before punctuation with comma and space
                modified = f"{core}, {append_phrase} X{append_count}{punct}"
                updated = True

    if updated or message.attachments:
        # Save updated counters if text was modified
        if updated:
            save_counters(counters_data)

        # Prepare attachment files before deleting the message
        files = [await att.to_file() for att in message.attachments]

        # Delete the original message
        await message.delete()

        # Send via webhook (reusing channel webhook)
        webhook = await get_channel_webhook(message.channel)
        await webhook.send(
            content=modified if updated else None,  # None if only attachments
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            wait=True,
            files=files
        )

    await bot.process_commands(message)

# -----------------------------
# Slash command: /track
# -----------------------------
@bot.tree.command(name="track", description="Track a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to track")
async def track(interaction: discord.Interaction, phrase: str):
    data = load_tracking()
    user_id = str(interaction.user.id)

    if user_id not in data:
        data[user_id] = []

    existing_lower = [p.lower() for p in data[user_id]]
    if phrase.lower() in existing_lower:
        await interaction.response.send_message(
            f"You are already tracking '{phrase}'!", ephemeral=True
        )
        return

    data[user_id].append(phrase)
    save_tracking(data)
    await interaction.response.send_message(
        f"✅ You are now tracking: '{phrase}'", ephemeral=True
    )

# -----------------------------
# Slash command: /untrack
# -----------------------------
@bot.tree.command(name="untrack", description="Stop tracking a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to stop tracking")
async def untrack(interaction: discord.Interaction, phrase: str):
    data = load_tracking()
    user_id = str(interaction.user.id)

    if user_id not in data:
        await interaction.response.send_message(
            f"❌ You are not tracking any phrases!", ephemeral=True
        )
        return

    matched_phrase = next((p for p in data[user_id] if p.lower() == phrase.lower()), None)
    if not matched_phrase:
        await interaction.response.send_message(
            f"❌ You are not tracking '{phrase}'!", ephemeral=True
        )
        return

    data[user_id].remove(matched_phrase)
    if not data[user_id]:
        del data[user_id]

    save_tracking(data)
    await interaction.response.send_message(
        f"✅ You have stopped tracking: '{phrase}'", ephemeral=True
    )

# -----------------------------
# Slash command: /set
# -----------------------------
@bot.tree.command(
    name="set",
    description="Set the counter for a tracked phrase",
    guild=guild
)
@app_commands.describe(
    phrase="The phrase whose counter you want to set",
    count="The number to set the counter to (0 resets the counter so the next message starts at 1)"
)
async def set_counter(interaction: discord.Interaction, phrase: str, count: int):
    if count < 0:
        await interaction.response.send_message(
            "❌ Counter cannot be negative.",
            ephemeral=True
        )
        return

    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    counters_data = load_counters()

    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}

    counters_data[user_id][channel_id][phrase] = count
    save_counters(counters_data)
    await interaction.response.send_message(
        f"✅ Counter for '{phrase}' in this channel has been set to {count}.",
        ephemeral=True
    )

# -----------------------------
# Slash command: /append
# -----------------------------
@bot.tree.command(
    name="append",
    description="Append a tracked phrase to the end of each sentence",
    guild=guild
)
@app_commands.describe(
    phrase="A currently tracked phrase to append to sentences"
)
async def append_command(interaction: discord.Interaction, phrase: str):
    user_id = str(interaction.user.id)
    tracking_data = load_tracking()
    append_data = load_append()

    if user_id not in tracking_data or phrase not in tracking_data[user_id]:
        await interaction.response.send_message(
            f"❌ You can only append a phrase you are currently tracking.",
            ephemeral=True
        )
        return

    append_data[user_id] = phrase
    save_append(append_data)
    await interaction.response.send_message(
        f"✅ Messages you send will now have '{phrase}' appended to the end of sentences according to rules.",
        ephemeral=True
    )

# -----------------------------
# Bot ready
# -----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=guild)
    print(f"✅ Logged in as {bot.user} and slash commands synced for guild {GUILD_ID}")

# -----------------------------
# Start the bot
# -----------------------------
bot.run(TOKEN)
