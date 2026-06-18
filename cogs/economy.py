import discord
from discord import app_commands
from discord.ext import commands

from config import DAILY_REWARD
from database import Database
from utils.helpers import send_reply


def format_seconds(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}h {minutes}m {secs}s"


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db  # type: ignore[attr-defined]

    @commands.hybrid_command(name="balance", description="Check your chip balance")
    async def balance(self, ctx: commands.Context) -> None:
        balance = await self.db.get_balance(ctx.author.id)
        await send_reply(
            ctx,
            ctx.interaction,
            f"💰 {ctx.author.display_name}, you have **{balance:,}** chips.",
        )

    @commands.hybrid_command(name="daily", description="Claim your daily chips")
    async def daily(self, ctx: commands.Context) -> None:
        can_claim, remaining = await self.db.can_claim_daily(ctx.author.id)
        if not can_claim:
            await send_reply(
                ctx,
                ctx.interaction,
                f"⏳ Daily already claimed. Come back in **{format_seconds(remaining)}**.",
                ephemeral=True,
            )
            return

        new_balance = await self.db.claim_daily(ctx.author.id, DAILY_REWARD)
        await send_reply(
            ctx,
            ctx.interaction,
            f"🎁 You claimed **{DAILY_REWARD:,}** chips!\n"
            f"New balance: **{new_balance:,}** chips.",
        )

    @commands.hybrid_command(name="givechips", aliases=["give"], description="Give chips to another player")
    @app_commands.describe(
        member="Player to receive chips",
        amount="Amount of chips to give",
    )
    async def givechips(
        self,
        ctx: commands.Context,
        member: discord.Member,
        amount: commands.Range[int, 1, 100_000_000],
    ) -> None:
        if member.id == ctx.author.id:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ You can't give chips to yourself.",
                ephemeral=True,
            )
            return
        if member.bot:
            await send_reply(
                ctx,
                ctx.interaction,
                "❌ You can only give chips to real players.",
                ephemeral=True,
            )
            return

        sender_balance = await self.db.get_balance(ctx.author.id)
        if sender_balance < amount:
            await send_reply(
                ctx,
                ctx.interaction,
                f"❌ Not enough chips. You have **{sender_balance:,}**.",
                ephemeral=True,
            )
            return

        await self.db.adjust_balance(ctx.author.id, -amount)
        try:
            recipient_balance = await self.db.adjust_balance(member.id, amount)
        except Exception:
            await self.db.adjust_balance(ctx.author.id, amount)
            raise

        updated_sender_balance = sender_balance - amount
        await send_reply(
            ctx,
            ctx.interaction,
            f"✅ {ctx.author.mention} gave **{amount:,}** chips to {member.mention}.\n"
            f"Your new balance: **{updated_sender_balance:,}** | "
            f"{member.display_name}'s balance: **{recipient_balance:,}**",
        )

    @commands.hybrid_command(name="leaderboard", description="Top chip balances")
    async def leaderboard(self, ctx: commands.Context) -> None:
        rows = await self.db.leaderboard()
        if not rows:
            await send_reply(ctx, ctx.interaction, "No players yet.")
            return

        lines = []
        for index, (user_id, balance) in enumerate(rows, start=1):
            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    user = None
            name = user.display_name if user else f"User {user_id}"
            lines.append(f"**{index}.** {name} — **{balance:,}** chips")

        embed = discord.Embed(title="🏆 Leaderboard", description="\n".join(lines))
        await send_reply(ctx, ctx.interaction, embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
