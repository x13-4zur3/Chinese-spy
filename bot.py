import asyncio
import sys

import discord
from discord.ext import commands

from config import DEFAULT_PREFIX, DISCORD_TOKEN
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


bot = commands.Bot(command_prefix=get_prefixes, intents=intents, help_command=None)
bot.db = Database()


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


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("Slash commands synced.")
    print(f"Default prefix: {DEFAULT_PREFIX} (per-server prefix is configurable via /settings)")


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument. Try `{ctx.prefix}help` for usage.")
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


async def main() -> None:
    if not DISCORD_TOKEN:
        print("Missing DISCORD_TOKEN in .env")
        sys.exit(1)

    await bot.db.connect()
    async with bot:
        await load_extensions()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
