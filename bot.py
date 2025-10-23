import discord
from discord.ext import commands
from discord import app_commands

# Read token and guild ID
with open("bot.token", "r") as f:
    TOKEN = f.read().strip()
with open("guild.id", "r") as f:
    GUILD_ID = int(f.read().strip())

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# Message-delete and repost logic
# -----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await message.delete()
    webhook = await message.channel.create_webhook(name=message.author.display_name)
    await webhook.send(
        message.content,
        username=message.author.display_name,
        avatar_url=message.author.display_avatar.url
    )
    await webhook.delete()
    await bot.process_commands(message)

# -----------------------------
# Slash command: /say
# -----------------------------
guild = discord.Object(id=GUILD_ID)

@bot.tree.command(name="say", description="Repeat your message", guild=guild)
@app_commands.describe(message="The text you want the bot to repeat")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(f"{interaction.user.display_name} says: {message}")

# -----------------------------
# Bot ready event
# -----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=guild)  # Sync only to this guild
    print(f"✅ Logged in as {bot.user} and slash commands synced for guild {GUILD_ID}")

# -----------------------------
# Start the bot
# -----------------------------
bot.run(TOKEN)
