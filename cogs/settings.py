from __future__ import annotations

import discord
from discord.ext import commands

from database import Database, GuildSettings


def settings_embed(settings: GuildSettings) -> discord.Embed:
    log_channel = f"<#{settings.log_channel_id}>" if settings.log_channel_id else "Not set"
    embed = discord.Embed(
        title="⚙️ Server Settings",
        description="Use the menu below to configure this server.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Prefix", value=f"`{settings.prefix}`", inline=True)
    embed.add_field(name="Log channel", value=log_channel, inline=True)
    embed.add_field(name="Casino enabled", value="Yes" if settings.casino_enabled else "No", inline=True)
    embed.add_field(name="Coinflip house edge", value=f"{settings.coinflip_house_edge}%", inline=True)
    embed.add_field(name="Log member events", value="On" if settings.log_member_events else "Off", inline=True)
    embed.add_field(name="Log message events", value="On" if settings.log_message_events else "Off", inline=True)
    embed.add_field(name="Log moderation events", value="On" if settings.log_mod_events else "Off", inline=True)
    embed.add_field(name="Log game events", value="On" if settings.log_game_events else "Off", inline=True)
    embed.set_footer(text="Changes save instantly.")
    return embed


class PrefixModal(discord.ui.Modal, title="Change command prefix"):
    prefix = discord.ui.TextInput(
        label="Prefix",
        placeholder="!",
        min_length=1,
        max_length=5,
        default="!",
    )

    def __init__(self, cog: "SettingsCog", guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.db.update_guild_settings(
            self.guild_id,
            prefix=str(self.prefix.value).strip(),
        )
        await interaction.response.edit_message(embed=settings_embed(settings), view=SettingsView(self.cog, self.guild_id))


class HouseEdgeModal(discord.ui.Modal, title="Coinflip house edge"):
    edge = discord.ui.TextInput(
        label="House edge percent (0-10)",
        placeholder="0",
        min_length=1,
        max_length=2,
        default="0",
    )

    def __init__(self, cog: "SettingsCog", guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = max(0, min(10, int(str(self.edge.value).strip())))
        except ValueError:
            await interaction.response.send_message("Enter a number from 0 to 10.", ephemeral=True)
            return

        settings = await self.cog.db.update_guild_settings(
            self.guild_id,
            coinflip_house_edge=value,
        )
        await interaction.response.edit_message(embed=settings_embed(settings), view=SettingsView(self.cog, self.guild_id))


class SettingsView(discord.ui.View):
    def __init__(self, cog: "SettingsCog", guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.select(
        placeholder="Choose a setting to change...",
        options=[
            discord.SelectOption(label="Set prefix", value="prefix", description="Change the text command prefix"),
            discord.SelectOption(label="Set log channel", value="log_channel", description="Pick a channel for server logs"),
            discord.SelectOption(label="Toggle casino games", value="casino", description="Enable or disable casino commands"),
            discord.SelectOption(label="Set coinflip house edge", value="house_edge", description="0% = fair 50/50 win chance"),
            discord.SelectOption(label="Toggle member logs", value="member_logs", description="Join and leave logging"),
            discord.SelectOption(label="Toggle message logs", value="message_logs", description="Edit and delete logging"),
            discord.SelectOption(label="Toggle moderation logs", value="mod_logs", description="Ban, kick, and purge logging"),
            discord.SelectOption(label="Toggle game logs", value="game_logs", description="Casino game result logging"),
        ],
    )
    async def setting_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need **Manage Server** to change settings.",
                ephemeral=True,
            )
            return

        choice = select.values[0]
        settings = await self.cog.db.get_guild_settings(self.guild_id)

        if choice == "prefix":
            await interaction.response.send_modal(PrefixModal(self.cog, self.guild_id))
            return

        if choice == "house_edge":
            await interaction.response.send_modal(HouseEdgeModal(self.cog, self.guild_id))
            return

        if choice == "log_channel":
            await interaction.response.send_message(
                "Pick the log channel below.",
                ephemeral=True,
                view=LogChannelView(self.cog, self.guild_id),
            )
            return

        updates: dict[str, object] = {}
        if choice == "casino":
            updates["casino_enabled"] = not settings.casino_enabled
        elif choice == "member_logs":
            updates["log_member_events"] = not settings.log_member_events
        elif choice == "message_logs":
            updates["log_message_events"] = not settings.log_message_events
        elif choice == "mod_logs":
            updates["log_mod_events"] = not settings.log_mod_events
        elif choice == "game_logs":
            updates["log_game_events"] = not settings.log_game_events

        updated = await self.cog.db.update_guild_settings(self.guild_id, **updates)
        await interaction.response.edit_message(embed=settings_embed(updated), view=self)


class LogChannelView(discord.ui.View):
    def __init__(self, cog: "SettingsCog", guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select a log channel",
        channel_types=[discord.ChannelType.text],
    )
    async def pick_channel(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect,
    ) -> None:
        channel = select.values[0]
        await self.cog.db.update_guild_settings(
            self.guild_id,
            log_channel_id=channel.id,
        )
        await interaction.response.send_message(
            f"Log channel set to {channel.mention}.",
            ephemeral=True,
        )


class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db  # type: ignore[attr-defined]

    @commands.hybrid_command(name="settings", description="Open the server settings menu")
    @commands.has_permissions(manage_guild=True)
    async def settings(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        settings = await self.db.get_guild_settings(ctx.guild.id)
        view = SettingsView(self, ctx.guild.id)
        embed = settings_embed(settings)

        if ctx.interaction:
            await ctx.interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await ctx.send(embed=embed, view=view)

    @settings.error
    async def settings_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need **Manage Server** to use `/settings`.")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
