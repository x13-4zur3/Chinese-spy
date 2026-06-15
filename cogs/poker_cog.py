from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import Database
from games.poker import HAND_TYPE_MAP, PokerSeat, PokerTableGame, pretty_card
from utils.helpers import send_reply


class RaiseModal(discord.ui.Modal, title="Raise amount"):
    amount = discord.ui.TextInput(
        label="Raise by (chips)",
        placeholder="100",
        min_length=1,
        max_length=10,
    )

    def __init__(self, cog: "PokerCog", channel_id: int, minimum_bet: int):
        super().__init__()
        self.cog = cog
        self.channel_id = channel_id
        self.amount.default = str(minimum_bet)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(str(self.amount.value).strip().replace(",", ""))
        except ValueError:
            await interaction.response.send_message("Enter a valid number.", ephemeral=True)
            return
        await self.cog._handle_action(interaction, "raise", value)


class NewTableModal(discord.ui.Modal, title="Start a new poker table"):
    minimum_bet = discord.ui.TextInput(
        label="Minimum bet / raise (chips)",
        placeholder="100",
        min_length=1,
        max_length=10,
    )
    include_bot = discord.ui.TextInput(
        label="Include house bot? (yes/no)",
        placeholder="no",
        required=False,
        max_length=3,
    )

    def __init__(self, cog: "PokerCog", channel_id: int, default_bet: int, owner_id: int):
        super().__init__()
        self.cog = cog
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.minimum_bet.default = str(default_bet)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            bet = int(str(self.minimum_bet.value).strip().replace(",", ""))
        except ValueError:
            await interaction.response.send_message("Enter a valid minimum bet.", ephemeral=True)
            return
        if bet < 1:
            await interaction.response.send_message("Minimum bet must be at least 1.", ephemeral=True)
            return

        bot_answer = str(self.include_bot.value or "no").strip().lower()
        with_bot = bot_answer in {"yes", "y", "true", "1"}
        await self.cog._create_table_from_interaction(
            interaction,
            bet=bet,
            include_bot=with_bot,
            owner_id=self.owner_id,
        )


class PokerLobbyView(discord.ui.View):
    def __init__(self, cog: "PokerCog", channel_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id

    @discord.ui.button(label="Join Table", style=discord.ButtonStyle.success, emoji="➕")
    async def join_table(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._join_from_button(interaction, self.channel_id)

    @discord.ui.button(label="Add Bot", style=discord.ButtonStyle.secondary, emoji="🤖")
    async def add_bot(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._add_bot_from_button(interaction, self.channel_id)

    @discord.ui.button(label="Start Hand", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_hand(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._start_from_button(interaction, self.channel_id)


class PokerGameView(discord.ui.View):
    def __init__(self, cog: "PokerCog", channel_id: int, table: PokerTableGame):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id
        self._sync_buttons(table)

    def _sync_buttons(self, table: PokerTableGame) -> None:
        actor = table.current_actor()
        actor_id = actor.user_id if actor and not actor.is_bot else None

        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue

            custom_id = item.custom_id or ""
            if custom_id == "poker:my_cards":
                item.disabled = table.finished
                continue

            if table.finished:
                item.disabled = True
                continue

            if custom_id.startswith("poker:action:"):
                item.disabled = actor_id is None
                continue

    @discord.ui.button(
        label="Check / Call",
        style=discord.ButtonStyle.primary,
        custom_id="poker:action:check_call",
        row=0,
    )
    async def check_call(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        table = self.cog.active_tables.get(self.channel_id)
        if table is None:
            await interaction.response.send_message("No active table here.", ephemeral=True)
            return
        seat_index = table.user_index(interaction.user.id)
        if seat_index is None:
            await interaction.response.send_message("You are not seated.", ephemeral=True)
            return
        to_call = table.to_call_for_index(seat_index)
        action = "call" if to_call > 0 else "check"
        await self.cog._handle_action(interaction, action, 0)

    @discord.ui.button(
        label="Fold",
        style=discord.ButtonStyle.danger,
        custom_id="poker:action:fold",
        row=0,
    )
    async def fold(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_action(interaction, "fold", 0)

    @discord.ui.button(
        label="Bet Min",
        style=discord.ButtonStyle.success,
        custom_id="poker:action:bet",
        row=1,
    )
    async def bet_min(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        table = self.cog.active_tables.get(self.channel_id)
        if table is None:
            await interaction.response.send_message("No active table here.", ephemeral=True)
            return
        await self.cog._handle_action(interaction, "bet", table.minimum_bet)

    @discord.ui.button(
        label="Raise Min",
        style=discord.ButtonStyle.success,
        custom_id="poker:action:raise",
        row=1,
    )
    async def raise_min(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        table = self.cog.active_tables.get(self.channel_id)
        if table is None:
            await interaction.response.send_message("No active table here.", ephemeral=True)
            return
        await self.cog._handle_action(interaction, "raise", table.minimum_bet)

    @discord.ui.button(
        label="Custom Raise",
        style=discord.ButtonStyle.secondary,
        custom_id="poker:action:raise_custom",
        row=1,
    )
    async def raise_custom(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        table = self.cog.active_tables.get(self.channel_id)
        if table is None:
            await interaction.response.send_message("No active table here.", ephemeral=True)
            return
        actor = table.current_actor()
        if actor is None or actor.user_id != interaction.user.id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return
        await interaction.response.send_modal(
            RaiseModal(self.cog, self.channel_id, table.minimum_bet)
        )

    @discord.ui.button(
        label="My Cards",
        style=discord.ButtonStyle.secondary,
        emoji="🃏",
        custom_id="poker:my_cards",
        row=2,
    )
    async def my_cards(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        table = self.cog.active_tables.get(self.channel_id)
        if table is None or not table.started:
            await interaction.response.send_message("No active poker hand here.", ephemeral=True)
            return

        seat_index = table.user_index(interaction.user.id)
        if seat_index is None:
            await interaction.response.send_message(
                "Only seated players can view private cards.",
                ephemeral=True,
            )
            return

        seat = table.seats[seat_index]
        cards = " ".join(pretty_card(card) for card in seat.hole_cards)
        status = "folded" if seat.folded else "active"
        await interaction.response.send_message(
            f"🃏 **Your hole cards** (only you can see this)\n"
            f"{cards}\n\n"
            f"Board: {table.board_text()}\n"
            f"Pot: **{table.pot:,}** | Current bet: **{table.current_bet:,}** | Status: **{status}**",
            ephemeral=True,
        )


class PokerFinishedView(discord.ui.View):
    def __init__(self, cog: "PokerCog", channel_id: int, default_bet: int, owner_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id
        self.default_bet = default_bet
        self.owner_id = owner_id

    @discord.ui.button(label="New Table", style=discord.ButtonStyle.primary, emoji="🔄")
    async def new_table(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.channel_id in self.cog.active_tables:
            await interaction.response.send_message(
                "A poker table is already open in this channel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            NewTableModal(self.cog, self.channel_id, self.default_bet, interaction.user.id)
        )


class PokerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db  # type: ignore[attr-defined]
        self.active_tables: dict[int, PokerTableGame] = {}
        self.player_table: dict[int, int] = {}
        self.table_messages: dict[int, int] = {}
        self.last_minimum_bet: dict[int, int] = {}
        if not hasattr(bot, "active_casino_players"):
            bot.active_casino_players = set()  # type: ignore[attr-defined]
        self.active_casino_players: set[int] = bot.active_casino_players  # type: ignore[attr-defined]

    async def _casino_enabled(self, member: discord.Member) -> bool:
        settings = await self.db.get_guild_settings(member.guild.id)
        return settings.casino_enabled

    def _seat_name(self, seat: PokerSeat) -> str:
        if seat.is_bot or seat.user_id is None:
            return "🤖 House Bot"
        return f"<@{seat.user_id}>"

    def _lobby_embed(self, table: PokerTableGame) -> discord.Embed:
        embed = discord.Embed(
            title="♠️ Poker Table Lobby",
            description="Use the buttons below — no typing needed.",
            color=discord.Color.dark_green(),
        )
        embed.add_field(name="Minimum bet / raise", value=f"{table.minimum_bet:,} chips", inline=True)
        embed.add_field(name="Host", value=f"<@{table.owner_id}>", inline=True)
        players = "\n".join(self._seat_name(seat) for seat in table.seats) or "No players yet."
        embed.add_field(name="Seats", value=players, inline=False)
        embed.add_field(
            name="Buttons",
            value=(
                "➕ **Join Table** — take a seat\n"
                "🤖 **Add Bot** — host adds house bot\n"
                "▶️ **Start Hand** — host starts (needs 2+ seats)"
            ),
            inline=False,
        )
        return embed

    def _table_embed(self, table: PokerTableGame) -> discord.Embed:
        embed = discord.Embed(
            title=f"♠️ Poker — {table.stage_label()}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Board", value=table.board_text(), inline=False)
        embed.add_field(name="Pot", value=f"{table.pot:,} chips", inline=True)
        embed.add_field(name="Current bet", value=f"{table.current_bet:,}", inline=True)
        embed.add_field(name="Min bet/raise", value=f"{table.minimum_bet:,}", inline=True)

        actor = table.current_actor()
        if actor and not table.finished:
            embed.add_field(name="Current turn", value=self._seat_name(actor), inline=False)

        lines: list[str] = []
        payouts = table.payouts_by_index() if table.finished else {}
        for idx, seat in enumerate(table.seats):
            status: list[str] = []
            if seat.folded:
                status.append("folded")
            if not table.finished and idx == table.turn_index:
                status.append("acting")
            if table.finished and idx in table.winner_indexes:
                status.append("winner")

            committed = table.total_commitments.get(idx, 0)
            round_committed = table.round_commitments.get(idx, 0)
            line = f"{self._seat_name(seat)} — in pot **{committed:,}**"
            if not table.finished:
                line += f", round **{round_committed:,}**"
            if status:
                line += f" ({', '.join(status)})"
            if table.finished:
                payout = payouts.get(idx, 0)
                line += f" | payout **{payout:,}** | net **{table.net_by_index(idx):+,}**"
                if idx in table.hand_classes:
                    line += f" | {HAND_TYPE_MAP.get(table.hand_classes[idx], 'Unknown')}"
            lines.append(line)

        embed.add_field(name="Players", value="\n".join(lines) or "No players.", inline=False)

        if table.finished:
            reveal_lines = []
            for idx, seat in enumerate(table.seats):
                cards = " ".join(pretty_card(card) for card in seat.hole_cards)
                reveal_lines.append(f"{self._seat_name(seat)}: {cards}")
            embed.add_field(name="Showdown cards", value="\n".join(reveal_lines), inline=False)

        if table.action_history:
            embed.add_field(
                name="Recent actions",
                value="\n".join(f"• {entry}" for entry in table.action_history[-5:]),
                inline=False,
            )

        if not table.finished:
            embed.set_footer(text="Use buttons: Check/Call, Fold, Bet Min, Raise Min, Custom Raise, or My Cards (private).")
        return embed

    def _finished_embed(self, table: PokerTableGame) -> discord.Embed:
        embed = self._table_embed(table)
        embed.title = "♠️ Poker — Hand Complete"
        embed.color = discord.Color.green()
        embed.description = (
            "Payouts have been sent. This hand is over.\n"
            "Press **New Table** to start again with a new minimum bet/raise."
        )
        return embed

    async def _get_channel(self, channel_id: int) -> discord.TextChannel | None:
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def _update_table_message(
        self,
        channel_id: int,
        *,
        embed: discord.Embed,
        view: discord.ui.View | None,
        content: str | None = None,
    ) -> None:
        message_id = self.table_messages.get(channel_id)
        if message_id is None:
            return
        channel = await self._get_channel(channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(content=content, embed=embed, view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    def _clear_player_locks(self, table: PokerTableGame) -> None:
        for seat in table.seats:
            if seat.is_bot or seat.user_id is None:
                continue
            self.player_table.pop(seat.user_id, None)
            self.active_casino_players.discard(seat.user_id)

    async def _apply_payouts(self, table: PokerTableGame, guild: discord.Guild | None) -> None:
        payouts = table.payouts_by_index()
        for idx, seat in enumerate(table.seats):
            if seat.is_bot or seat.user_id is None:
                continue
            payout = payouts.get(idx, 0)
            if payout > 0:
                await self.db.adjust_balance(seat.user_id, payout)

        logger = self.bot.get_cog("ServerLogging")
        if logger and guild:
            winner_names = ", ".join(self._seat_name(table.seats[idx]) for idx in table.winner_indexes)
            await logger.log_game_event(  # type: ignore[attr-defined]
                guild,
                f"♠️ **Poker** — hand finished. Winners: {winner_names or 'None'} "
                f"(pot: {table.pot:,} chips).",
            )

    async def _complete_hand(self, channel_id: int, table: PokerTableGame, guild: discord.Guild | None) -> None:
        await self._apply_payouts(table, guild)
        self.last_minimum_bet[channel_id] = table.minimum_bet
        self.active_tables.pop(channel_id, None)
        self._clear_player_locks(table)

        finished_view = PokerFinishedView(
            self,
            channel_id,
            table.minimum_bet,
            table.owner_id,
        )
        await self._update_table_message(
            channel_id,
            embed=self._finished_embed(table),
            view=finished_view,
            content="✅ **Hand finished. Payouts delivered.**",
        )

    async def _run_bot_turns(self, table: PokerTableGame) -> list[str]:
        updates: list[str] = []
        safety_counter = 0
        while table.should_take_bot_turn() and not table.finished:
            safety_counter += 1
            if safety_counter > 20:
                break
            action, amount = table.bot_turn_decision()
            seat_index = table.turn_index
            required = table.required_chips_for_index(seat_index, action, amount)
            update = table.apply_action_by_index(
                seat_index,
                action,
                amount=amount,
                committed=required,
            )
            updates.append(f"🤖 {update}")
        return updates

    async def _handle_action(
        self,
        interaction: discord.Interaction,
        action: str,
        amount: int = 0,
    ) -> None:
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Poker only works in server channels.", ephemeral=True)
            return

        channel_id = interaction.channel.id
        table = self.active_tables.get(channel_id)
        if table is None or not table.started:
            await interaction.response.send_message("No active poker hand in this channel.", ephemeral=True)
            return
        if table.finished:
            await interaction.response.send_message("This hand is already over.", ephemeral=True)
            return
        if not table.has_user(interaction.user.id):
            await interaction.response.send_message("You are not seated at this table.", ephemeral=True)
            return

        actor = table.current_actor()
        if actor is None or actor.user_id != interaction.user.id:
            await interaction.response.send_message(
                f"It's {self._seat_name(actor)}'s turn." if actor else "No active turn.",
                ephemeral=True,
            )
            return

        if amount < 0:
            await interaction.response.send_message("Amount must be non-negative.", ephemeral=True)
            return

        try:
            required = table.required_human_chips(interaction.user.id, action, amount)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        deducted = 0
        if required > 0:
            balance = await self.db.get_balance(interaction.user.id)
            if balance < required:
                await interaction.response.send_message(
                    f"Not enough chips. Need **{required:,}**, have **{balance:,}**.",
                    ephemeral=True,
                )
                return
            await self.db.adjust_balance(interaction.user.id, -required)
            deducted = required

        try:
            update = table.apply_human_action(
                interaction.user.id,
                action,
                amount=amount,
                committed=required,
            )
        except ValueError as exc:
            if deducted > 0:
                await self.db.adjust_balance(interaction.user.id, deducted)
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        await interaction.response.defer()
        bot_updates = await self._run_bot_turns(table)
        action_lines = [f"• {update}", *[f"• {entry}" for entry in bot_updates]]

        if table.finished:
            await self._update_table_message(
                channel_id,
                embed=self._table_embed(table),
                view=None,
                content="\n".join(action_lines),
            )
            await self._complete_hand(channel_id, table, interaction.guild)
            return

        game_view = PokerGameView(self, channel_id, table)
        await self._update_table_message(
            channel_id,
            embed=self._table_embed(table),
            view=game_view,
            content="\n".join(action_lines) if action_lines else None,
        )

    async def _create_table(
        self,
        member: discord.Member,
        channel: discord.abc.MessageableChannel,
        *,
        bet: int,
        include_bot: bool,
        owner_id: int | None = None,
        interaction: discord.Interaction | None = None,
        ctx: commands.Context | None = None,
        replace_message: bool = False,
    ) -> None:
        if not isinstance(channel, discord.TextChannel):
            await send_reply(
                ctx,
                interaction,
                "Poker tables must be created in a text channel.",
                ephemeral=True,
            )
            return

        channel_id = channel.id
        if channel_id in self.active_tables:
            await send_reply(
                ctx,
                interaction,
                "This channel already has an active poker table.",
                ephemeral=True,
            )
            return

        host_id = owner_id or member.id
        if member.id in self.active_casino_players:
            await send_reply(
                ctx,
                interaction,
                "You are already in another active casino table.",
                ephemeral=True,
            )
            return

        table = PokerTableGame(minimum_bet=bet, owner_id=host_id)
        table.add_human(member.id, member.display_name)
        if include_bot:
            table.add_bot()

        self.active_tables[channel_id] = table
        self.player_table[member.id] = channel_id
        self.active_casino_players.add(member.id)

        view = PokerLobbyView(self, channel_id)
        embed = self._lobby_embed(table)

        if replace_message and channel_id in self.table_messages:
            await self._update_table_message(channel_id, embed=embed, view=view, content=None)
            return

        message = await send_reply(ctx, interaction, embed=embed, view=view)
        self.table_messages[channel_id] = message.id

    async def _create_table_from_interaction(
        self,
        interaction: discord.Interaction,
        *,
        bet: int,
        include_bot: bool,
        owner_id: int,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        if not await self._casino_enabled(interaction.user):
            await interaction.response.send_message("Casino games are disabled.", ephemeral=True)
            return
        if interaction.channel is None:
            await interaction.response.send_message("Invalid channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self._create_table(
            interaction.user,
            interaction.channel,
            bet=bet,
            include_bot=include_bot,
            owner_id=owner_id,
            interaction=interaction,
            replace_message=True,
        )
        await interaction.followup.send("🔄 New poker table created.", ephemeral=True)

    async def _join_player(self, member: discord.Member, channel_id: int) -> str | None:
        if not await self._casino_enabled(member):
            return "Casino games are disabled on this server."

        table = self.active_tables.get(channel_id)
        if table is None:
            return "No poker lobby in this channel."
        if table.started:
            return "This hand already started."
        if member.id in self.active_casino_players:
            if table.has_user(member.id):
                return "You are already seated at this table."
            return "You are already in another active casino table."
        if not table.add_human(member.id, member.display_name):
            return "Could not join (table may be full)."

        self.player_table[member.id] = channel_id
        self.active_casino_players.add(member.id)
        await self._update_table_message(
            channel_id,
            embed=self._lobby_embed(table),
            view=PokerLobbyView(self, channel_id),
        )
        return None

    async def _join_from_button(self, interaction: discord.Interaction, channel_id: int) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Server only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        error = await self._join_player(interaction.user, channel_id)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return
        await interaction.followup.send("✅ You joined the table.", ephemeral=True)

    async def _add_bot_from_button(self, interaction: discord.Interaction, channel_id: int) -> None:
        table = self.active_tables.get(channel_id)
        if table is None:
            await interaction.response.send_message("No poker lobby in this channel.", ephemeral=True)
            return
        if interaction.user.id != table.owner_id:
            await interaction.response.send_message("Only the host can add the bot.", ephemeral=True)
            return
        if table.started:
            await interaction.response.send_message("Hand already started.", ephemeral=True)
            return
        if not table.add_bot():
            await interaction.response.send_message("Bot is already seated or table is full.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self._update_table_message(channel_id, embed=self._lobby_embed(table), view=PokerLobbyView(self, channel_id))
        await interaction.followup.send("🤖 House bot joined.", ephemeral=True)

    async def _start_hand_for_channel(
        self,
        member: discord.Member,
        channel_id: int,
        guild: discord.Guild,
    ) -> str | None:
        table = self.active_tables.get(channel_id)
        if table is None:
            return "No poker lobby in this channel."
        if table.started:
            return "This hand already started."
        if member.id != table.owner_id:
            return "Only the host can start the hand."

        error = await self._validate_start(table)
        if error:
            return error

        table.start_hand()
        bot_updates = await self._run_bot_turns(table)
        content = "\n".join(f"• {u}" for u in bot_updates) if bot_updates else "Hand started. Use the buttons below."

        if table.finished:
            await self._update_table_message(
                channel_id,
                embed=self._table_embed(table),
                view=None,
                content=content,
            )
            await self._complete_hand(channel_id, table, guild)
            return None

        game_view = PokerGameView(self, channel_id, table)
        await self._update_table_message(
            channel_id,
            embed=self._table_embed(table),
            view=game_view,
            content=content,
        )
        return None

    async def _start_from_button(self, interaction: discord.Interaction, channel_id: int) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        error = await self._start_hand_for_channel(interaction.user, channel_id, interaction.guild)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return
        await interaction.followup.send("▶️ Hand started!", ephemeral=True)

    async def _validate_start(self, table: PokerTableGame) -> str | None:
        if len(table.seats) < 2:
            return "Need at least 2 seats (players and/or bot)."
        if table.human_count() < 2 and not any(seat.is_bot for seat in table.seats):
            return "Need at least 2 human players unless the bot is included."

        short_funds: list[str] = []
        for seat in table.seats:
            if seat.is_bot or seat.user_id is None:
                continue
            balance = await self.db.get_balance(seat.user_id)
            if balance < table.minimum_bet:
                short_funds.append(f"<@{seat.user_id}> ({balance:,})")
        if short_funds:
            return (
                f"These players need at least **{table.minimum_bet:,}** chips:\n"
                + "\n".join(short_funds)
            )
        return None

    @commands.hybrid_command(name="poker", description="Create a multiplayer Texas Hold'em table")
    @app_commands.describe(
        bet="Minimum bet and raise amount",
        include_bot="Include the house bot as a poker player",
    )
    async def poker(
        self,
        ctx: commands.Context,
        bet: commands.Range[int, 1, 1_000_000],
        include_bot: bool = False,
    ) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            await send_reply(ctx, ctx.interaction, "Poker only works in a server channel.", ephemeral=True)
            return
        if not await self._casino_enabled(ctx.author):
            await send_reply(ctx, ctx.interaction, "Casino games are disabled.", ephemeral=True)
            return
        if ctx.channel is None:
            await send_reply(ctx, ctx.interaction, "Could not resolve channel.", ephemeral=True)
            return

        await self._create_table(
            ctx.author,
            ctx.channel,
            bet=bet,
            include_bot=include_bot,
            ctx=ctx,
        )

    @commands.hybrid_command(name="poker_join", description="Join the poker table in this channel")
    async def poker_join(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None or ctx.channel is None:
            await send_reply(ctx, ctx.interaction, "Server channel only.", ephemeral=True)
            return

        error = await self._join_player(ctx.author, ctx.channel.id)
        if error:
            await send_reply(ctx, ctx.interaction, error, ephemeral=True)
            return
        await send_reply(ctx, ctx.interaction, "✅ You joined the table.", ephemeral=True)

    @commands.hybrid_command(name="poker_start", description="Start the poker hand in this channel")
    async def poker_start(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None or ctx.channel is None:
            await send_reply(ctx, ctx.interaction, "Server channel only.", ephemeral=True)
            return

        error = await self._start_hand_for_channel(ctx.author, ctx.channel.id, ctx.guild)
        if error:
            await send_reply(ctx, ctx.interaction, error, ephemeral=True)
            return
        await send_reply(ctx, ctx.interaction, "▶️ Hand started! Use the buttons on the table message.", ephemeral=True)

    @commands.hybrid_command(name="poker_action", description="Take a poker action (buttons are easier)")
    @app_commands.describe(action="check, call, bet, raise, or fold", amount="Amount for bet or raise")
    async def poker_action(
        self,
        ctx: commands.Context,
        action: str,
        amount: int = 0,
    ) -> None:
        if ctx.interaction:
            await self._handle_action(ctx.interaction, action.lower().strip(), amount)
        else:
            await send_reply(
                ctx,
                None,
                "Use the **buttons on the poker table message** instead of typing actions.",
            )

    @commands.hybrid_command(name="poker_hand", description="View your private hole cards")
    async def poker_hand(self, ctx: commands.Context) -> None:
        if ctx.channel is None or ctx.interaction is None:
            await send_reply(ctx, None, "Use the **My Cards** button on the table message (only you can see your cards).")
            return
        table = self.active_tables.get(ctx.channel.id)
        if table is None or not table.started:
            await send_reply(ctx, ctx.interaction, "No active poker hand here.", ephemeral=True)
            return
        seat_index = table.user_index(ctx.author.id)
        if seat_index is None:
            await send_reply(ctx, ctx.interaction, "You are not seated.", ephemeral=True)
            return
        seat = table.seats[seat_index]
        cards = " ".join(pretty_card(card) for card in seat.hole_cards)
        await send_reply(
            ctx,
            ctx.interaction,
            f"🃏 Your cards: {cards}\nBoard: {table.board_text()}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PokerCog(bot))
