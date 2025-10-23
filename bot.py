import discord
from discord.ext import commands

# 🔑 Read your bot token from the file 'bot.token'
with open("bot.token", "r") as f:
    TOKEN = f.read().strip()

intents = discord.Intents.default()
intents.message_content = True  # needed to read message text

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

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

# Start the bot with the token read from 'bot.token'
bot.run(TOKEN)
