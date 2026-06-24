import asyncio
import sys
import os

import discord
from discord.ext import commands

from config import DEFAULT_PREFIX, DISCORD_TOKEN, VOICE_CHANNEL_ID
from database import Database

print("=== BOT STARTUP ===")
print("VOICE_CHANNEL_ID =", VOICE_CHANNEL_ID)

# -----------------------------
# INTENTS
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True


# -----------------------------
# PREFIX SYSTEM
# -----------------------------
async def get_prefixes(bot: commands.Bot, message: discord.Message) -> list[str]:
    prefixes: list[str] = []

    if message.guild:
        settings = await bot.db.get_guild_settings(message.guild.id)
        prefixes.append(settings.prefix)
    else:
        prefixes.append(DEFAULT_PREFIX)

    if bot.user:
        prefixes.append(f"<@{bot.user.id}> ")
        prefixes.append(f"<@!{bot.user.id}> ")

    return prefixes


bot = commands.Bot(
    command_prefix=get_prefixes,
    intents=intents,
    help_command=None
)

bot.db = Database()


# -----------------------------
# LOAD EXTENSIONS
# -----------------------------
async def load_extensions() -> None:
    extensions = [
        "cogs.logging_cog",
        "cogs.economy",
        "cogs.coinflip",
        "cogs.blackjack_cog",
        "cogs.poker_cog",
        "cogs.settings",
        "cogs.moderation",
    ]

    for extension in extensions:
        await bot.load_extension(extension)


# -----------------------------
# VOICE AUTO JOIN
# -----------------------------
async def connect_to_voice():
    print("=== CONNECT_TO_VOICE STARTED ===")

    try:
        await bot.wait_until_ready()

        print(f"VOICE_CHANNEL_ID = {VOICE_CHANNEL_ID}")

        print("Guilds:")
        for guild in bot.guilds:
            print(f" - {guild.name} ({guild.id})")

        channel = bot.get_channel(VOICE_CHANNEL_ID)

        print(f"Cached channel: {channel}")

        if channel is None:
            print("Channel not in cache. Fetching...")
            channel = await bot.fetch_channel(VOICE_CHANNEL_ID)

        print(f"Fetched channel: {channel}")
        print(f"Channel type: {type(channel)}")

        if not isinstance(channel, discord.VoiceChannel):
            print("ERROR: Channel is not a VoiceChannel")
            return

        permissions = channel.permissions_for(channel.guild.me)

        print("Permissions:")
        print(f" View Channel: {permissions.view_channel}")
        print(f" Connect: {permissions.connect}")
        print(f" Speak: {permissions.speak}")

        if bot.voice_clients:
            print("Already connected")
            return

        vc = await channel.connect()

        print(f"SUCCESS: Connected to {vc.channel.name}")

    except Exception:
        import traceback
        traceback.print_exc()

# -----------------------------
# VOICE RECONNECT
# -----------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    if bot.user is None:
        return

    if member.id != bot.user.id:
        return

    if after.channel is None:
        await asyncio.sleep(3)

        try:
            channel = await bot.fetch_channel(VOICE_CHANNEL_ID)
            await channel.connect()
            print("🔁 Reconnected to VC")
        except Exception as e:
            print(f"Reconnect failed: {repr(e)}")


# -----------------------------
# READY EVENT
# -----------------------------
@bot.event
async def on_ready():
    print("================================")
    print("ON_READY FIRED")
    print("================================")

    try:
        await bot.tree.sync()
        print("Slash commands synced")
    except Exception as e:
        print(f"Slash sync failed: {e}")

    print(f"Logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Default prefix: {DEFAULT_PREFIX}")
    print(f"Voice channel ID: {VOICE_CHANNEL_ID}")

    await asyncio.sleep(10)

    asyncio.create_task(connect_to_voice())

# -----------------------------
# ERROR HANDLER
# -----------------------------
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument. Try `{ctx.prefix}help`")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {error}")
        return
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You don't have permission to run that command.")
        return
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Slow down — try again in **{error.retry_after:.1f}s**.")
        return

    raise error

@bot.command()
async def vc(ctx):
    try:
        channel = await bot.fetch_channel(VOICE_CHANNEL_ID)

        await channel.connect()

        await ctx.send("Joined VC")
    except Exception as e:
        await ctx.send(f"VC Error: {e}")

# -----------------------------
# MAIN STARTUP
# -----------------------------
async def main() -> None:
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN is missing")
        sys.exit(1)

    await bot.db.connect()

    async with bot:
        await load_extensions()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
