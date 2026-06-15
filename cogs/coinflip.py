import secrets

import discord
from discord import app_commands
from discord.ext import commands

from database import Database
from utils.helpers import resolve_choice, send_reply


COIN_SIDES = ("heads", "tails")


def roll_coin_result(pick: str, house_edge: int) -> tuple[str, bool, float]:
    """
    Resolve the result with even-money payouts and configurable win/loss odds.
    House edge shifts win chance from 50.0% down to 45.0% (edge 0-10).
    """
    edge = max(0, min(10, house_edge))
    win_chance_basis_points = 5000 - (edge * 50)
    won = secrets.randbelow(10_000) < win_chance_basis_points
    if won:
        outcome = pick
    else:
        outcome = COIN_SIDES[0] if pick == COIN_SIDES[1] else COIN_SIDES[1]
    return outcome, won, win_chance_basis_points / 100


class Coinflip(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db  # type: ignore[attr-defined]

    async def _run_coinflip(
        self,
        user: discord.User | discord.Member,
        bet: int,
        choice: str,
        *,
        ctx: commands.Context | None = None,
        interaction: discord.Interaction | None = None,
    ) -> None:
        pick = resolve_choice(choice)
        if pick not in {"heads", "tails"}:
            await send_reply(
                ctx,
                interaction,
                "❌ Pick **heads** or **tails**.",
                ephemeral=True,
            )
            return

        balance = await self.db.get_balance(user.id)
        if bet > balance:
            await send_reply(
                ctx,
                interaction,
                f"❌ Not enough chips. Balance: **{balance:,}**.",
                ephemeral=True,
            )
            return

        house_edge = 0
        if isinstance(user, discord.Member) and user.guild:
            settings = await self.db.get_guild_settings(user.guild.id)
            if not settings.casino_enabled:
                await send_reply(
                    ctx,
                    interaction,
                    "❌ Casino games are disabled on this server.",
                    ephemeral=True,
                )
                return
            house_edge = settings.coinflip_house_edge

        await self.db.adjust_balance(user.id, -bet)
        outcome, won, win_chance = roll_coin_result(pick, house_edge)

        if won:
            new_balance = await self.db.adjust_balance(user.id, bet * 2)
        else:
            new_balance = await self.db.get_balance(user.id)

        result_text = "You won!" if won else "You lost."
        color = discord.Color.green() if won else discord.Color.red()

        embed = discord.Embed(title="🪙 Coinflip", color=color)
        embed.add_field(name="Your pick", value=pick.title(), inline=True)
        embed.add_field(name="Result", value=outcome.title(), inline=True)
        embed.add_field(name="Bet", value=f"{bet:,}", inline=True)
        embed.add_field(name="Outcome", value=result_text, inline=False)
        embed.add_field(name="New balance", value=f"{new_balance:,} chips", inline=False)
        if house_edge:
            embed.set_footer(
                text=f"Win chance: {win_chance:.1f}% (house edge {house_edge}%, set in /settings)"
            )
        else:
            embed.set_footer(text="Fair 50/50 odds — win chance 50.0%, payout returns 2× your bet.")

        await send_reply(ctx, interaction, embed=embed)

        logger = self.bot.get_cog("ServerLogging")
        if logger and isinstance(user, discord.Member):
            await logger.log_game_event(  # type: ignore[attr-defined]
                user.guild,
                f"🪙 **Coinflip** — {user.mention} bet **{bet:,}** on **{pick.title()}**, "
                f"got **{outcome.title()}** — {'won' if won else 'lost'}.",
            )

    @commands.hybrid_command(name="coinflip", description="Bet on heads or tails")
    @app_commands.describe(bet="Amount to bet", choice="Heads or tails")
    @app_commands.choices(
        choice=[
            app_commands.Choice(name="Heads", value="heads"),
            app_commands.Choice(name="Tails", value="tails"),
        ]
    )
    async def coinflip(
        self,
        ctx: commands.Context,
        bet: commands.Range[int, 1, 1_000_000],
        choice: str,
    ) -> None:
        interaction = ctx.interaction
        await self._run_coinflip(ctx.author, bet, choice, ctx=ctx, interaction=interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Coinflip(bot))
