import discord
from discord.ext import commands

# Read your bot token from the file 'bot.token'
with open("bot.token", "r") as f:
    TOKEN = f.read().strip()

# Enable the intents your bot needs
intents = discord.Intents.default()
intents.message_content = True  # required for reading message text

# Create the bot object with a prefix (commands start with "!")
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("Bot is connected and ready!")

@bot.command()
async def ping(ctx):
    """Replies with Pong! to test the connection."""
    await ctx.send("🏓 Pong!")

# Start the bot
bot.run(TOKEN)
