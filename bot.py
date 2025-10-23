import json
import os
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
# Guild object for slash commands
# -----------------------------
guild = discord.Object(id=GUILD_ID)

# -----------------------------
# Message-delete and repost logic with counters
# -----------------------------
@bot.event
@bot.event
async def on_message(message):
    if message.author.bot:
        return  # ignore bot messages

    user_id = str(message.author.id)
    channel_id = str(message.channel.id)
    tracking_data = load_tracking()
    counters_data = load_counters()

    if user_id not in tracking_data:
        await bot.process_commands(message)
        return  # user tracks nothing, do nothing

    user_phrases = tracking_data[user_id]
    content_lower = message.content.lower()
    modified = message.content  # will hold the modified message
    updated = False

    # Initialize counters structure
    if user_id not in counters_data:
        counters_data[user_id] = {}
    if channel_id not in counters_data[user_id]:
        counters_data[user_id][channel_id] = {}

    # Process each phrase left-to-right
    for phrase in user_phrases:
        phrase_lower = phrase.lower()
        start = 0
        while True:
            index = content_lower.find(phrase_lower, start)
            if index == -1:
                break
            # Get current counter
            count = counters_data[user_id][channel_id].get(phrase, 1)
            # Append " X{count}" after the phrase in the original message
            before = modified[:index + len(phrase)]
            after = modified[index + len(phrase):]
            modified = before + f" X{count}" + after
            # Increment counter
            counters_data[user_id][channel_id][phrase] = count + 1
            # Move start index past this occurrence (including appended counter)
            start = index + len(phrase) + len(f" X{count}")
            updated = True
            # Also update content_lower so subsequent searches align with original case-insensitive matching
            content_lower = modified.lower()

    if updated:
        # Save updated counters
        save_counters(counters_data)

        # Delete and repost message via webhook (ignore replies)
        await message.delete()
        webhook = await message.channel.create_webhook(name=message.author.display_name)
        await webhook.send(
            modified,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            wait=True
        )
        await webhook.delete()

    await bot.process_commands(message)

# -----------------------------
# Slash command: /track (case-insensitive)
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
# Slash command: /untrack (case-insensitive)
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
