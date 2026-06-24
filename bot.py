import asyncio
import sys

import discord
from discord.ext import commands

from config import DEFAULT_PREFIX, DISCORD_TOKEN, VOICE_CHANNEL_ID
from database import Database


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True


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
# EXTENSIONS
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
# VOICE AUTO JOIN LOGIC
# -----------------------------
async def connect_to_voice():
    await bot.wait_until_ready()

    channel = bot.get_channel(VOICE_CHANNEL_ID)

    if not channel:
        print("❌ Voice channel not found")
        return

    if not isinstance(channel, discord.VoiceChannel):
        print("❌ Invalid voice channel ID")
        return

    # already connected somewhere
    if bot.voice_clients:
        return

    try:
        await channel.connect()
        print(f"🔊 Joined voice channel: {channel.name}")
    except Exception as e:
        print(f"❌ Failed to join VC: {e}")


@bot.event
async def on_voice_state_update(member, before, after):
    # only care about bot itself
    if bot.user is None:
        return

    if member.id != bot.user.id:
        return

    # if disconnected, reconnect
    if after.channel is None:
        await asyncio.sleep(3)  # small delay prevents Discord race conditions

        channel = bot.get_channel(VOICE_CHANNEL_ID)
        if channel:
            try:
                await channel.connect()
                print("🔁 Reconnected to VC")
            except Exception as e:
                print(f"Reconnect failed: {e}")


# -----------------------------
# READY EVENT
# -----------------------------
@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("Slash commands synced.")
    print(f"Default prefix: {DEFAULT_PREFIX}")


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


# -----------------------------
# MAIN STARTUP
# -----------------------------
async def main() -> None:
    if not DISCORD_TOKEN:
        print("Missing DISCORD_TOKEN in .env")
        sys.exit(1)

    await bot.db.connect()

    async with bot:
        await load_extensions()

        # start voice task
        asyncio.create_task(connect_to_voice())

        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
