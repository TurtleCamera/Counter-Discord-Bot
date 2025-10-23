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

# Path to JSON file
TRACK_FILE = "tracked_phrases.json"

# -----------------------------
# Helper functions for tracking
# -----------------------------
def load_tracking():
    """Load tracking data from the JSON file, create file if it doesn't exist."""
    if not os.path.exists(TRACK_FILE):
        with open(TRACK_FILE, "w") as f:
            json.dump({}, f)  # start with empty dict
        return {}
    with open(TRACK_FILE, "r") as f:
        return json.load(f)

def save_tracking(data):
    """Save tracking data to JSON file."""
    with open(TRACK_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------
# Guild object for slash commands
# -----------------------------
guild = discord.Object(id=GUILD_ID)

# -----------------------------
# Message-delete and repost logic
# -----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return  # ignore bot messages

    # Delete the original message
    await message.delete()

    # Create a temporary webhook to repost the message
    webhook = await message.channel.create_webhook(name=message.author.display_name)
    await webhook.send(
        message.content,
        username=message.author.display_name,
        avatar_url=message.author.display_avatar.url
    )
    await webhook.delete()  # clean up the webhook

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

    if phrase in data[user_id]:
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
# Slash command: /remove
# -----------------------------
@bot.tree.command(name="remove", description="Stop tracking a phrase", guild=guild)
@app_commands.describe(phrase="The phrase you want to remove from tracking")
async def remove(interaction: discord.Interaction, phrase: str):
    data = load_tracking()
    user_id = str(interaction.user.id)

    if user_id not in data or phrase not in data[user_id]:
        await interaction.response.send_message(
            f"❌ You are not tracking '{phrase}'!", ephemeral=True
        )
        return

    data[user_id].remove(phrase)
    # Clean up empty list to keep JSON tidy
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
