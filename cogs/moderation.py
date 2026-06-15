from __future__ import annotations

from datetime import timedelta

import discord
from discord.ext import commands

from database import Database
from utils.helpers import send_reply


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db  # type: ignore[attr-defined]

    async def _log_mod_action(self, guild: discord.Guild, title: str, description: str) -> None:
        settings = await self.db.get_guild_settings(guild.id)
        if not settings.log_mod_events:
            return
        logger = self.bot.get_cog("ServerLogging")
        if logger:
            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.dark_orange(),
                timestamp=discord.utils.utcnow(),
            )
            await logger.send_log(guild, embed, enabled=True)  # type: ignore[attr-defined]

    async def _validate_target_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        action: str,
    ) -> bool:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return False
        if not isinstance(ctx.author, discord.Member):
            await send_reply(
                ctx,
                ctx.interaction,
                "Unable to verify your role hierarchy for this command.",
                ephemeral=True,
            )
            return False

        author = ctx.author
        guild = ctx.guild
        bot_member = guild.me

        if member.id == author.id:
            await send_reply(
                ctx,
                ctx.interaction,
                f"You cannot {action} yourself.",
                ephemeral=True,
            )
            return False
        if member.id == guild.owner_id:
            await send_reply(
                ctx,
                ctx.interaction,
                f"You cannot {action} the server owner.",
                ephemeral=True,
            )
            return False
        if bot_member and member.id == bot_member.id:
            await send_reply(
                ctx,
                ctx.interaction,
                f"I cannot {action} myself.",
                ephemeral=True,
            )
            return False
        if author.id != guild.owner_id and member.top_role >= author.top_role:
            await send_reply(
                ctx,
                ctx.interaction,
                f"You cannot {action} someone with an equal or higher role.",
                ephemeral=True,
            )
            return False
        if bot_member and member.top_role >= bot_member.top_role:
            await send_reply(
                ctx,
                ctx.interaction,
                f"I cannot {action} someone with an equal or higher role than me.",
                ephemeral=True,
            )
            return False

        return True

    async def _apply_timeout(
        self,
        ctx: commands.Context,
        member: discord.Member,
        minutes: int,
        reason: str,
    ) -> None:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return
        if not await self._validate_target_member(ctx, member, "timeout"):
            return

        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        try:
            await member.timeout(until, reason=reason)
        except discord.Forbidden:
            await send_reply(
                ctx,
                ctx.interaction,
                "I don't have permission to timeout that member.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await send_reply(
                ctx,
                ctx.interaction,
                "Failed to apply timeout due to a Discord API error.",
                ephemeral=True,
            )
            return

        await send_reply(
            ctx,
            ctx.interaction,
            f"🔇 Muted {member.mention} for **{minutes}** minute(s). Reason: {reason}",
        )
        await self._log_mod_action(
            ctx.guild,
            "🔇 Member muted",
            (
                f"{ctx.author.mention} muted {member.mention} (`{member.id}`) for **{minutes}m**.\n"
                f"**Reason:** {reason}"
            ),
        )

    async def _remove_timeout(self, ctx: commands.Context, member: discord.Member) -> None:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return
        if not await self._validate_target_member(ctx, member, "remove timeout from"):
            return

        try:
            await member.timeout(None, reason=f"Timeout removed by {ctx.author}")
        except discord.Forbidden:
            await send_reply(
                ctx,
                ctx.interaction,
                "I don't have permission to remove timeout from that member.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await send_reply(
                ctx,
                ctx.interaction,
                "Failed to remove timeout due to a Discord API error.",
                ephemeral=True,
            )
            return

        await send_reply(ctx, ctx.interaction, f"✅ Removed mute from {member.mention}.")
        await self._log_mod_action(
            ctx.guild,
            "✅ Member unmuted",
            f"{ctx.author.mention} removed mute from {member.mention} (`{member.id}`).",
        )

    @commands.hybrid_command(name="help", description="Show available commands")
    async def help_command(self, ctx: commands.Context) -> None:
        prefix = "!"
        if ctx.guild:
            settings = await self.db.get_guild_settings(ctx.guild.id)
            prefix = settings.prefix

        embed = discord.Embed(
            title="🤖 Casino Bot Help",
            description=(
                "This bot supports **slash commands** and **prefix commands**.\n"
                f"Current prefix: `{prefix}`"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Casino",
            value=(
                f"`{prefix}balance` / `/balance`\n"
                f"`{prefix}daily` / `/daily`\n"
                f"`{prefix}give @user <amount>` / `/givechips`\n"
                f"`{prefix}leaderboard` / `/leaderboard`\n"
                f"`{prefix}coinflip <bet> <heads|tails>`\n"
                f"`{prefix}blackjack <bet>`\n"
                f"`{prefix}poker <bet>` — then use **buttons** on the table message"
            ),
            inline=False,
        )
        embed.add_field(
            name="Poker buttons",
            value=(
                "Lobby: **Join**, **Add Bot**, **Start Hand**\n"
                "In-game: **Check/Call**, **Fold**, **Bet Min**, **Raise Min**, **Custom Raise**\n"
                "**My Cards** — only you see your cards (ephemeral)\n"
                "After payout: **New Table** — set a new min bet/raise"
            ),
            inline=False,
        )
        embed.add_field(
            name="Server tools",
            value=(
                f"`{prefix}settings` / `/settings`\n"
                f"`{prefix}setup` / `/setup`\n"
                f"`{prefix}serverinfo` / `/serverinfo`\n"
                f"`{prefix}userinfo [@user]`\n"
                f"`{prefix}purge <amount>`\n"
                f"`{prefix}kick @user [reason]`\n"
                f"`{prefix}ban @user [reason]`\n"
                f"`{prefix}unban <user_id> [reason]`\n"
                f"`{prefix}timeout @user <minutes> [reason]`\n"
                f"`{prefix}mute @user <minutes> [reason]`\n"
                f"`{prefix}untimeout @user`\n"
                f"`{prefix}unmute @user`\n"
                f"`{prefix}slowmode <seconds>`\n"
                f"`{prefix}avatar [@user]`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Prefix commands",
            value=(
                f"Default prefix is `{prefix}`. Change it in `/settings`.\n"
                f"Example: `{prefix}coinflip 100 heads` or `{prefix}poker 50`"
            ),
            inline=False,
        )
        embed.set_footer(text="Use /settings to configure prefix, logs, and casino options.")
        await send_reply(ctx, ctx.interaction, embed=embed)

    @commands.hybrid_command(name="setup", description="Quick setup guide for this server")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return

        settings = await self.db.get_guild_settings(ctx.guild.id)
        log_channel = f"<#{settings.log_channel_id}>" if settings.log_channel_id else "Not set yet"

        embed = discord.Embed(
            title="🛠️ Server Setup Guide",
            description="Follow these steps to configure the bot on your server.",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="1. Set a log channel",
            value="Run `/settings` → **Set log channel** and pick a private staff channel.",
            inline=False,
        )
        embed.add_field(
            name="2. Choose your prefix",
            value=f"Current prefix: `{settings.prefix}`\nChange it in `/settings` → **Set prefix**.",
            inline=False,
        )
        embed.add_field(
            name="3. Enable logging",
            value=(
                "In `/settings`, toggle member, message, moderation, and game logs as needed.\n"
                f"Current log channel: {log_channel}"
            ),
            inline=False,
        )
        embed.add_field(
            name="4. Test commands",
            value=(
                f"`{settings.prefix}help` or `/help`\n"
                f"`{settings.prefix}balance` — check chips\n"
                f"`{settings.prefix}coinflip 50 heads` — test casino"
            ),
            inline=False,
        )
        embed.set_footer(text="You gave the bot Administrator — it can manage channels, roles, and logs.")
        await send_reply(ctx, ctx.interaction, embed=embed)

    @setup.error
    async def setup_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await send_reply(ctx, ctx.interaction, "You need **Manage Server** to use setup.", ephemeral=True)
        else:
            raise error

    @commands.hybrid_command(name="kick", description="Kick a member from the server")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return
        if not await self._validate_target_member(ctx, member, "kick"):
            return

        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            await send_reply(ctx, ctx.interaction, "I don't have permission to kick that member.", ephemeral=True)
            return
        except discord.HTTPException:
            await send_reply(ctx, ctx.interaction, "Failed to kick member due to a Discord API error.", ephemeral=True)
            return

        await send_reply(ctx, ctx.interaction, f"👢 Kicked {member.mention}. Reason: {reason}")
        await self._log_mod_action(
            ctx.guild,
            "👢 Member kicked",
            (
                f"{ctx.author.mention} kicked {member.mention} (`{member.id}`).\n"
                f"**Reason:** {reason}"
            ),
        )

    @commands.hybrid_command(name="ban", description="Ban a member from the server")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return
        if not await self._validate_target_member(ctx, member, "ban"):
            return

        try:
            await member.ban(reason=reason, delete_message_days=0)
        except discord.Forbidden:
            await send_reply(ctx, ctx.interaction, "I don't have permission to ban that member.", ephemeral=True)
            return
        except discord.HTTPException:
            await send_reply(ctx, ctx.interaction, "Failed to ban member due to a Discord API error.", ephemeral=True)
            return

        await send_reply(ctx, ctx.interaction, f"🔨 Banned {member.mention}. Reason: {reason}")
        await self._log_mod_action(
            ctx.guild,
            "🔨 Member banned",
            (
                f"{ctx.author.mention} banned {member.mention} (`{member.id}`).\n"
                f"**Reason:** {reason}"
            ),
        )

    @commands.hybrid_command(name="unban", description="Unban a user by ID")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(
        self,
        ctx: commands.Context,
        user_id: str,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return

        try:
            user_id_int = int(user_id)
        except ValueError:
            await send_reply(ctx, ctx.interaction, "Invalid user ID.", ephemeral=True)
            return

        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id_int))
        except discord.NotFound:
            await send_reply(ctx, ctx.interaction, "That user is not currently banned.", ephemeral=True)
            return
        except discord.Forbidden:
            await send_reply(ctx, ctx.interaction, "I can't view the server ban list.", ephemeral=True)
            return
        except discord.HTTPException:
            await send_reply(ctx, ctx.interaction, "Failed to read ban list due to a Discord API error.", ephemeral=True)
            return

        user = ban_entry.user
        try:
            await ctx.guild.unban(user, reason=reason)
        except discord.Forbidden:
            await send_reply(ctx, ctx.interaction, "I don't have permission to unban that user.", ephemeral=True)
            return
        except discord.HTTPException:
            await send_reply(ctx, ctx.interaction, "Failed to unban user due to a Discord API error.", ephemeral=True)
            return

        await send_reply(ctx, ctx.interaction, f"♻️ Unbanned `{user}` ({user.id}).")
        await self._log_mod_action(
            ctx.guild,
            "♻️ Member unbanned",
            (
                f"{ctx.author.mention} unbanned {user.mention} (`{user.id}`).\n"
                f"**Reason:** {reason}"
            ),
        )

    @commands.hybrid_command(name="timeout", description="Timeout (mute) a member")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(
        self,
        ctx: commands.Context,
        member: discord.Member,
        minutes: commands.Range[int, 1, 40320],
        *,
        reason: str = "No reason provided",
    ) -> None:
        await self._apply_timeout(ctx, member, minutes, reason)

    @commands.hybrid_command(name="mute", description="Mute a member (alias for timeout)")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        minutes: commands.Range[int, 1, 40320],
        *,
        reason: str = "No reason provided",
    ) -> None:
        await self._apply_timeout(ctx, member, minutes, reason)

    @commands.hybrid_command(name="untimeout", description="Remove a member's timeout")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, member: discord.Member) -> None:
        await self._remove_timeout(ctx, member)

    @commands.hybrid_command(name="unmute", description="Unmute a member (alias for untimeout)")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member) -> None:
        await self._remove_timeout(ctx, member)

    @commands.hybrid_command(name="slowmode", description="Set slowmode for the current channel")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(
        self,
        ctx: commands.Context,
        seconds: commands.Range[int, 0, 21600],
    ) -> None:
        if ctx.guild is None or not isinstance(ctx.channel, discord.TextChannel):
            await send_reply(ctx, ctx.interaction, "This command only works in text channels.")
            return

        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            msg = f"🐢 Slowmode disabled in {ctx.channel.mention}."
        else:
            msg = f"🐢 Slowmode set to **{seconds}** second(s) in {ctx.channel.mention}."
        await send_reply(ctx, ctx.interaction, msg)
        await self._log_mod_action(
            ctx.guild,
            "🐢 Slowmode updated",
            f"{ctx.author.mention} set slowmode to **{seconds}s** in {ctx.channel.mention}.",
        )

    @kick.error
    @ban.error
    @unban.error
    @timeout.error
    @mute.error
    @untimeout.error
    @unmute.error
    @slowmode.error
    async def mod_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await send_reply(ctx, ctx.interaction, "You don't have permission to use that command.", ephemeral=True)
        elif isinstance(error, commands.BotMissingPermissions):
            await send_reply(ctx, ctx.interaction, "I don't have the required permissions for that action.", ephemeral=True)
        else:
            raise error

    @commands.hybrid_command(name="serverinfo", description="Show server information")
    async def serverinfo(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "This command only works in a server.")
            return

        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "F"), inline=False)
        embed.add_field(name="Server ID", value=str(guild.id), inline=False)
        await send_reply(ctx, ctx.interaction, embed=embed)

    @commands.hybrid_command(name="userinfo", description="Show user information")
    async def userinfo(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        if not isinstance(member, discord.Member):
            member = ctx.author

        embed = discord.Embed(title=str(member), color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Mention", value=member.mention, inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, "F") if member.joined_at else "Unknown", inline=False)
        embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, "F"), inline=False)

        if ctx.guild:
            balance = await self.db.get_balance(member.id)
            embed.add_field(name="Chip balance", value=f"{balance:,}", inline=True)

        await send_reply(ctx, ctx.interaction, embed=embed)

    @commands.hybrid_command(name="avatar", description="Show a user's avatar")
    async def avatar(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.display_name}'s avatar")
        embed.set_image(url=member.display_avatar.url)
        await send_reply(ctx, ctx.interaction, embed=embed)

    @commands.hybrid_command(name="purge", description="Delete recent messages")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: commands.Range[int, 1, 100]) -> None:
        if ctx.guild is None or not isinstance(ctx.channel, discord.TextChannel):
            await send_reply(ctx, ctx.interaction, "This command only works in text channels.")
            return

        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)

        deleted = await ctx.channel.purge(limit=amount)
        await send_reply(
            ctx,
            ctx.interaction,
            f"🧹 Deleted **{len(deleted)}** messages.",
            ephemeral=True,
        )
        await self._log_mod_action(
            ctx.guild,
            "🧹 Messages purged",
            f"{ctx.author.mention} deleted **{len(deleted)}** messages in {ctx.channel.mention}.",
        )

    @purge.error
    async def purge_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await send_reply(
                ctx,
                ctx.interaction,
                "You need **Manage Messages** to use purge.",
                ephemeral=True,
            )
        elif isinstance(error, commands.BotMissingPermissions):
            await send_reply(
                ctx,
                ctx.interaction,
                "I need **Manage Messages** permission to purge.",
                ephemeral=True,
            )
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
