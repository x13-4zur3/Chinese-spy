from __future__ import annotations

import discord
from discord.ext import commands

from database import Database


class ServerLogging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db  # type: ignore[attr-defined]
        self._message_cache: dict[int, str] = {}

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = await self.db.get_guild_settings(guild.id)
        if not settings.log_channel_id:
            return None
        channel = guild.get_channel(settings.log_channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
        *,
        enabled: bool = True,
    ) -> None:
        if not enabled:
            return
        channel = await self._get_log_channel(guild)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    async def log_game_event(self, guild: discord.Guild, message: str) -> None:
        settings = await self.db.get_guild_settings(guild.id)
        if not settings.log_game_events:
            return
        embed = discord.Embed(description=message, color=discord.Color.gold())
        await self.send_log(guild, embed, enabled=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        self._message_cache[message.id] = message.content or ""

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or before.guild is None:
            return

        settings = await self.db.get_guild_settings(before.guild.id)
        if not settings.log_message_events:
            return

        old_content = self._message_cache.get(before.id, before.content or "")
        if old_content == (after.content or ""):
            return

        embed = discord.Embed(
            title="✏️ Message edited",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=old_content[:1000] or "(empty)", inline=False)
        embed.add_field(name="After", value=(after.content or "(empty)")[:1000], inline=False)
        embed.add_field(name="Jump", value=f"[Go to message]({after.jump_url})", inline=False)
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        settings = await self.db.get_guild_settings(message.guild.id)
        if not settings.log_message_events:
            return

        content = self._message_cache.pop(message.id, message.content or "(unknown)")
        embed = discord.Embed(
            title="🗑️ Message deleted",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Content", value=content[:1000] or "(empty)", inline=False)
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        settings = await self.db.get_guild_settings(member.guild.id)
        if not settings.log_member_events:
            return

        embed = discord.Embed(
            title="📥 Member joined",
            description=f"{member.mention} (`{member}`)",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Member count", value=str(member.guild.member_count), inline=True)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        settings = await self.db.get_guild_settings(member.guild.id)
        if not settings.log_member_events:
            return

        embed = discord.Embed(
            title="📤 Member left",
            description=f"{member.mention} (`{member}`)",
            color=discord.Color.dark_gray(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member count", value=str(member.guild.member_count), inline=True)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        settings = await self.db.get_guild_settings(guild.id)
        if not settings.log_mod_events:
            return

        embed = discord.Embed(
            title="🔨 Member banned",
            description=f"{user.mention} (`{user}`)",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:

        settings = await self.db.get_guild_settings(after.guild.id)

        if before.timed_out_until != after.timed_out_until and settings.log_mod_events:
            now = discord.utils.utcnow()
            if after.timed_out_until and after.timed_out_until > now:
                timeout_text = (
                    f"until {discord.utils.format_dt(after.timed_out_until, 'F')} "
                    f"({discord.utils.format_dt(after.timed_out_until, 'R')})"
                )
                embed = discord.Embed(
                    title="🔇 Member muted",
                    description=f"{after.mention} was muted {timeout_text}.",
                    color=discord.Color.dark_orange(),
                    timestamp=now,
                )
                await self.send_log(after.guild, embed)
            elif before.timed_out_until and before.timed_out_until > now:
                embed = discord.Embed(
                    title="🔊 Member unmuted",
                    description=f"{after.mention} is no longer muted.",
                    color=discord.Color.green(),
                    timestamp=now,
                )
                await self.send_log(after.guild, embed)

        if before.roles == after.roles or not settings.log_member_events:
            return

        added = [role for role in after.roles if role not in before.roles]
        removed = [role for role in before.roles if role not in after.roles]
        if not added and not removed:
            return

        lines = []
        if added:
            lines.append("**Added:** " + ", ".join(role.mention for role in added))
        if removed:
            lines.append("**Removed:** " + ", ".join(role.mention for role in removed))

        embed = discord.Embed(
            title="🎭 Roles updated",
            description=f"{after.mention}\n" + "\n".join(lines),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        await self.send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        settings = await self.db.get_guild_settings(guild.id)
        if not settings.log_mod_events:
            return

        embed = discord.Embed(
            title="♻️ Member unbanned",
            description=f"{user.mention} (`{user}`)",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        await self.send_log(guild, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerLogging(bot))
