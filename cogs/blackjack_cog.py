from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import Database
from games.blackjack import BlackjackTableGame, hand_value
from utils.helpers import send_reply


class BlackjackInviteView(discord.ui.View):
    def __init__(self, cog: "BlackjackCog", channel_id: int, invited_user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id
        self.invited_user_id = invited_user_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_invite(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await self.cog.handle_invite_button(interaction, self.channel_id, accepted=True)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_invite(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await self.cog.handle_invite_button(interaction, self.channel_id, accepted=False)


class BlackjackActionView(discord.ui.View):
    def __init__(
        self,
        cog: "BlackjackCog",
        channel_id: int,
        table: BlackjackTableGame | None = None,
    ):
        super().__init__(timeout=600)
        self.cog = cog
        self.channel_id = channel_id
        target_table = table if table is not None else self.cog.active_tables.get(channel_id)
        if target_table is None or target_table.finished:
            self._disable_all_buttons()
            return

        actor = target_table.current_player()
        if actor is None:
            self._disable_all_buttons()
            return

        if not target_table.can_double_for_user(actor.user_id):
            self.double_move.disabled = True

    def _disable_all_buttons(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_move(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await self.cog.handle_action_button(interaction, self.channel_id, action_value="hit")

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand_move(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await self.cog.handle_action_button(interaction, self.channel_id, action_value="stand")

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success)
    async def double_move(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await self.cog.handle_action_button(interaction, self.channel_id, action_value="double")


class BlackjackCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db  # type: ignore[attr-defined]
        self.active_tables: dict[int, BlackjackTableGame] = {}
        self.player_table: dict[int, int] = {}
        self.pending_invites: dict[int, int] = {}
        if not hasattr(bot, "active_casino_players"):
            bot.active_casino_players = set()  # type: ignore[attr-defined]
        self.active_casino_players: set[int] = bot.active_casino_players  # type: ignore[attr-defined]

    async def _casino_enabled(self, member: discord.Member) -> bool:
        settings = await self.db.get_guild_settings(member.guild.id)
        return settings.casino_enabled

    def _lobby_embed(
        self,
        table: BlackjackTableGame,
        invited_user_id: int | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(title="🃏 Blackjack Table Lobby")
        embed.add_field(name="Base bet", value=f"{table.base_bet:,} chips", inline=True)
        embed.add_field(name="Owner", value=f"<@{table.owner_id}>", inline=True)
        embed.add_field(name="Max players", value="2", inline=True)
        seats = "\n".join(f"<@{player.user_id}>" for player in table.players) or "No players yet."
        embed.add_field(name="Seats", value=seats, inline=False)

        if invited_user_id is not None:
            embed.add_field(
                name="Invite",
                value=f"Waiting for <@{invited_user_id}> to accept or decline.",
                inline=False,
            )

        join_step = "• `!blackjack_join` / `/blackjack_join` to join"
        if invited_user_id is not None:
            join_step = f"• <@{invited_user_id}> can accept/decline with the buttons below"

        embed.add_field(
            name="How to play",
            value=(
                f"{join_step}\n"
                "• `!blackjack_start` / `/blackjack_start` to begin\n"
                "• Use the Hit / Stand / Double buttons under the game embed"
            ),
            inline=False,
        )
        return embed

    def _table_embed(self, table: BlackjackTableGame) -> discord.Embed:
        hide_hole = not table.finished
        dealer_cards = " ".join(table.public_dealer_cards(hide_hole))
        dealer_total = "?" if hide_hole else str(hand_value(table.dealer))

        embed = discord.Embed(title="🃏 Multiplayer Blackjack")
        embed.add_field(
            name="Dealer",
            value=f"{dealer_cards}\nTotal: **{dealer_total}**",
            inline=False,
        )
        embed.add_field(name="Base bet", value=f"{table.base_bet:,} chips", inline=True)

        actor = table.current_player()
        if actor and not table.finished:
            embed.add_field(name="Current turn", value=f"<@{actor.user_id}>", inline=True)

        player_lines: list[str] = []
        for player in table.players:
            cards = " ".join(str(card) for card in player.hand)
            total = hand_value(player.hand)
            status: list[str] = []
            if not table.finished and actor and actor.user_id == player.user_id:
                status.append("acting")
            if player.busted:
                status.append("bust")
            if player.stood and not table.finished:
                status.append("stood")
            line = (
                f"<@{player.user_id}> — {cards}\n"
                f"Total: **{total}** | Bet: **{player.bet:,}**"
            )
            if status:
                line += f" ({', '.join(status)})"
            if table.finished and player.result is not None:
                result_labels = {
                    "blackjack": "Blackjack",
                    "win": "Win",
                    "lose": "Lose",
                    "push": "Push",
                    "bust": "Bust",
                    "dealer_bust": "Dealer bust",
                    "dealer_blackjack": "Dealer blackjack",
                }
                line += (
                    f"\nResult: **{result_labels.get(player.result, player.result)}**"
                    f" | Payout: **{player.payout:+,}**"
                )
            player_lines.append(line)

        embed.add_field(name="Players", value="\n\n".join(player_lines), inline=False)

        if table.action_log:
            embed.add_field(
                name="Recent actions",
                value="\n".join(f"• {entry}" for entry in table.action_log[-5:]),
                inline=False,
            )
        return embed

    def _action_view(
        self,
        channel_id: int,
        table: BlackjackTableGame | None = None,
    ) -> BlackjackActionView:
        return BlackjackActionView(self, channel_id, table)

    async def _finalize_table(
        self,
        channel_id: int,
        table: BlackjackTableGame,
        guild: discord.Guild | None,
    ) -> None:
        for player in table.players:
            if player.payout == 0:
                await self.db.adjust_balance(player.user_id, player.bet)
            elif player.payout > 0:
                await self.db.adjust_balance(player.user_id, player.bet + player.payout)

        logger = self.bot.get_cog("ServerLogging")
        if logger and guild:
            summary = ", ".join(
                f"<@{player.user_id}>:{player.result or 'unknown'}({player.payout:+,})"
                for player in table.players
            )
            await logger.log_game_event(  # type: ignore[attr-defined]
                guild,
                f"🃏 **Blackjack** — multiplayer hand finished: {summary}",
            )

        self.active_tables.pop(channel_id, None)
        self.pending_invites.pop(channel_id, None)
        for player in table.players:
            self.player_table.pop(player.user_id, None)
            self.active_casino_players.discard(player.user_id)

    async def _apply_player_action(
        self,
        table: BlackjackTableGame,
        user_id: int,
        action_value: str,
    ) -> str:
        if action_value == "hit":
            return table.hit(user_id)

        if action_value == "stand":
            return table.stand(user_id)

        if action_value != "double":
            raise ValueError("Action must be hit, stand, or double.")

        if not table.can_double_for_user(user_id):
            raise ValueError("You can only double on your first move this turn.")

        current = table.current_player()
        if current is None:
            raise ValueError("No active turn.")
        extra_bet = current.bet
        balance = await self.db.get_balance(user_id)
        if balance < extra_bet:
            raise ValueError(f"Not enough chips to double. Need {extra_bet:,}, have {balance:,}.")

        await self.db.adjust_balance(user_id, -extra_bet)
        try:
            return table.double(user_id)
        except ValueError:
            await self.db.adjust_balance(user_id, extra_bet)
            raise

    async def handle_invite_button(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        accepted: bool,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message(
                "❌ Blackjack multiplayer is only available in a server channel.",
                ephemeral=True,
            )
            return

        table = self.active_tables.get(channel_id)
        invited_user_id = self.pending_invites.get(channel_id)
        if table is None or invited_user_id is None or table.started:
            await interaction.response.send_message(
                "❌ This blackjack invite is no longer active.",
                ephemeral=True,
            )
            return

        if interaction.user.id != invited_user_id:
            await interaction.response.send_message(
                "❌ Only the invited player can accept or decline this game.",
                ephemeral=True,
            )
            return

        if accepted:
            if interaction.user.id in self.active_casino_players and not table.has_user(interaction.user.id):
                await interaction.response.send_message(
                    "❌ You are already in another active casino table.",
                    ephemeral=True,
                )
                return

            if not table.add_player(interaction.user.id, interaction.user.display_name):
                await interaction.response.send_message(
                    "❌ Couldn't join this blackjack table.",
                    ephemeral=True,
                )
                return

            self.player_table[interaction.user.id] = channel_id
            self.active_casino_players.add(interaction.user.id)
            self.pending_invites.pop(channel_id, None)
            await interaction.response.edit_message(
                content=f"✅ <@{interaction.user.id}> accepted the blackjack invite.",
                embed=self._lobby_embed(table),
                view=None,
            )
            return

        self.active_tables.pop(channel_id, None)
        self.pending_invites.pop(channel_id, None)
        for player in table.players:
            self.player_table.pop(player.user_id, None)
            self.active_casino_players.discard(player.user_id)

        await interaction.response.edit_message(
            content=f"❌ <@{interaction.user.id}> declined the blackjack invite. Table closed.",
            embed=None,
            view=None,
        )

    async def handle_action_button(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        action_value: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message(
                "❌ Blackjack multiplayer is only available in a server channel.",
                ephemeral=True,
            )
            return

        table = self.active_tables.get(channel_id)
        if table is None or not table.started:
            await interaction.response.send_message(
                "❌ No active blackjack hand in this channel.",
                ephemeral=True,
            )
            return
        if table.finished:
            await interaction.response.send_message(
                "❌ This blackjack hand already finished.",
                ephemeral=True,
            )
            return
        if not table.has_user(interaction.user.id):
            await interaction.response.send_message(
                "❌ You are not seated at this table.",
                ephemeral=True,
            )
            return

        actor = table.current_player()
        if actor is None:
            await interaction.response.send_message("❌ No active turn.", ephemeral=True)
            return
        if actor.user_id != interaction.user.id:
            await interaction.response.send_message(
                f"❌ It's <@{actor.user_id}>'s turn.",
                ephemeral=True,
            )
            return

        try:
            update = await self._apply_player_action(table, interaction.user.id, action_value)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        embed = self._table_embed(table)
        view = self._action_view(channel_id, table)
        if table.finished:
            await self._finalize_table(channel_id, table, interaction.guild)

        await interaction.response.edit_message(
            content=f"• {update}",
            embed=embed,
            view=view,
        )

    @commands.hybrid_command(name="blackjack", description="Create a multiplayer blackjack table")
    @app_commands.describe(
        bet="Base bet each player commits at hand start",
        opponent="Player to invite (optional)",
    )
    async def blackjack(
        self,
        ctx: commands.Context,
        bet: commands.Range[int, 1, 1_000_000],
        opponent: discord.Member | None = None,
    ) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ Blackjack multiplayer is only available in a server channel.",
                ephemeral=True,
            )
            return

        if not await self._casino_enabled(ctx.author):
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ Casino games are disabled on this server.",
                ephemeral=True,
            )
            return

        if ctx.channel is None:
            await send_reply(ctx, ctx.interaction, "❌ Could not resolve channel.", ephemeral=True)
            return

        channel_id = ctx.channel.id
        if channel_id in self.active_tables:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ This channel already has an active blackjack table.",
                ephemeral=True,
            )
            return

        if ctx.author.id in self.active_casino_players:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ You are already in another active casino table.",
                ephemeral=True,
            )
            return

        if opponent is not None:
            if opponent.id == ctx.author.id:
                await send_reply(
                    ctx,
                    ctx.interaction,
                    "❌ You can't invite yourself to blackjack.",
                    ephemeral=True,
                )
                return
            if opponent.bot:
                await send_reply(
                    ctx,
                    ctx.interaction,
                    "❌ You can only invite a human player.",
                    ephemeral=True,
                )
                return
            if opponent.id in self.active_casino_players:
                await send_reply(
                    ctx,
                    ctx.interaction,
                    "❌ That player is already in another active casino table.",
                    ephemeral=True,
                )
                return

        table = BlackjackTableGame(owner_id=ctx.author.id, base_bet=bet)
        table.add_player(ctx.author.id, ctx.author.display_name)
        self.active_tables[channel_id] = table
        self.player_table[ctx.author.id] = channel_id
        self.active_casino_players.add(ctx.author.id)

        view: BlackjackInviteView | None = None
        invited_user_id: int | None = None
        content: str | None = None
        if opponent is not None:
            invited_user_id = opponent.id
            self.pending_invites[channel_id] = invited_user_id
            view = BlackjackInviteView(self, channel_id, invited_user_id)
            content = f"🎯 <@{invited_user_id}>, you were invited to blackjack."

        await send_reply(
            ctx,
            ctx.interaction,
            content=content,
            embed=self._lobby_embed(table, invited_user_id=invited_user_id),
            view=view,
        )

    @commands.hybrid_command(name="blackjack_join", description="Join the blackjack table in this channel")
    async def blackjack_join(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ Blackjack multiplayer is only available in a server channel.",
                ephemeral=True,
            )
            return

        if not await self._casino_enabled(ctx.author):
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ Casino games are disabled on this server.",
                ephemeral=True,
            )
            return

        if ctx.channel is None:
            await send_reply(ctx, ctx.interaction, "❌ Could not resolve channel.", ephemeral=True)
            return

        channel_id = ctx.channel.id
        table = self.active_tables.get(channel_id)
        if table is None:
            await send_reply(ctx, ctx.interaction, "❌ No blackjack lobby in this channel.", ephemeral=True)
            return
        if table.started:
            await send_reply(ctx, ctx.interaction, "❌ This blackjack hand already started.", ephemeral=True)
            return

        invited_user_id = self.pending_invites.get(channel_id)
        if invited_user_id is not None and ctx.author.id != invited_user_id:
            await send_reply(
                ctx,
                ctx.interaction,
                f"❌ Only <@{invited_user_id}> can join this invited table.",
                ephemeral=True,
            )
            return

        if ctx.author.id in self.active_casino_players:
            if table.has_user(ctx.author.id):
                await send_reply(ctx, ctx.interaction, "You are already seated at this table.", ephemeral=True)
            else:
                await send_reply(
                    ctx,
                    ctx.interaction,
                    "❌ You are already in another active casino table.",
                    ephemeral=True,
                )
            return

        if not table.add_player(ctx.author.id, ctx.author.display_name):
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ This table is full (blackjack max is 2 players).",
                ephemeral=True,
            )
            return

        self.player_table[ctx.author.id] = channel_id
        self.active_casino_players.add(ctx.author.id)
        if invited_user_id == ctx.author.id:
            self.pending_invites.pop(channel_id, None)
            invited_user_id = None

        await send_reply(
            ctx,
            ctx.interaction,
            embed=self._lobby_embed(table, invited_user_id=invited_user_id),
        )

    @commands.hybrid_command(name="blackjack_start", description="Start the blackjack hand in this channel")
    async def blackjack_start(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ Blackjack multiplayer is only available in a server channel.",
                ephemeral=True,
            )
            return

        if ctx.channel is None:
            await send_reply(ctx, ctx.interaction, "❌ Could not resolve channel.", ephemeral=True)
            return

        channel_id = ctx.channel.id
        table = self.active_tables.get(channel_id)
        if table is None:
            await send_reply(ctx, ctx.interaction, "❌ No blackjack lobby in this channel.", ephemeral=True)
            return
        if table.started:
            await send_reply(ctx, ctx.interaction, "❌ This blackjack hand already started.", ephemeral=True)
            return
        if table.owner_id != ctx.author.id:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ Only the table owner can start the hand.",
                ephemeral=True,
            )
            return

        invited_user_id = self.pending_invites.get(channel_id)
        if invited_user_id is not None:
            await send_reply(
                ctx,
                ctx.interaction,
                f"❌ Waiting for <@{invited_user_id}> to accept or decline the invite.",
                ephemeral=True,
            )
            return

        if not table.players:
            await send_reply(ctx, ctx.interaction, "❌ No players are seated.", ephemeral=True)
            return

        short_funds: list[str] = []
        for player in table.players:
            balance = await self.db.get_balance(player.user_id)
            if balance < table.base_bet:
                short_funds.append(f"<@{player.user_id}> ({balance:,})")
        if short_funds:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ These players need at least "
                f"**{table.base_bet:,}** chips:\n" + "\n".join(short_funds),
                ephemeral=True,
            )
            return

        debited_users: list[int] = []
        try:
            for player in table.players:
                await self.db.adjust_balance(player.user_id, -table.base_bet)
                debited_users.append(player.user_id)
            table.start_hand()
        except ValueError as exc:
            for user_id in debited_users:
                await self.db.adjust_balance(user_id, table.base_bet)
            await send_reply(ctx, ctx.interaction, f"❌ {exc}", ephemeral=True)
            return

        await send_reply(
            ctx,
            ctx.interaction,
            embed=self._table_embed(table),
            view=self._action_view(channel_id, table),
        )
        if table.finished:
            await self._finalize_table(channel_id, table, ctx.guild)

    @commands.hybrid_command(name="blackjack_action", description="Take a blackjack action on your turn")
    @app_commands.describe(action="hit, stand, or double")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="hit", value="hit"),
            app_commands.Choice(name="stand", value="stand"),
            app_commands.Choice(name="double", value="double"),
        ]
    )
    async def blackjack_action(self, ctx: commands.Context, action: str) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ Blackjack multiplayer is only available in a server channel.",
                ephemeral=True,
            )
            return

        if ctx.channel is None:
            await send_reply(ctx, ctx.interaction, "❌ Could not resolve channel.", ephemeral=True)
            return

        channel_id = ctx.channel.id
        table = self.active_tables.get(channel_id)
        if table is None or not table.started:
            await send_reply(ctx, ctx.interaction, "❌ No active blackjack hand in this channel.", ephemeral=True)
            return
        if table.finished:
            await send_reply(ctx, ctx.interaction, "❌ This blackjack hand already finished.", ephemeral=True)
            return
        if not table.has_user(ctx.author.id):
            await send_reply(ctx, ctx.interaction, "❌ You are not seated at this table.", ephemeral=True)
            return

        actor = table.current_player()
        if actor is None:
            await send_reply(ctx, ctx.interaction, "❌ No active turn.", ephemeral=True)
            return
        if actor.user_id != ctx.author.id:
            await send_reply(
                ctx,
                ctx.interaction,
                f"❌ It's <@{actor.user_id}>'s turn.",
                ephemeral=True,
            )
            return

        action_value = action.lower().strip()
        try:
            update = await self._apply_player_action(table, ctx.author.id, action_value)
        except ValueError as exc:
            await send_reply(ctx, ctx.interaction, f"❌ {exc}", ephemeral=True)
            return

        await send_reply(
            ctx,
            ctx.interaction,
            content=f"• {update}",
            embed=self._table_embed(table),
            view=self._action_view(channel_id, table),
        )
        if table.finished:
            await self._finalize_table(channel_id, table, ctx.guild)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BlackjackCog(bot))
