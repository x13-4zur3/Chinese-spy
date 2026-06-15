from __future__ import annotations

import discord
from discord.ext import commands


def resolve_choice(choice: str | discord.app_commands.Choice[str]) -> str:
    if isinstance(choice, str):
        return choice.lower()
    return str(choice.value).lower()


async def send_reply(
    ctx: commands.Context | None,
    interaction: discord.Interaction | None,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = False,
    view: discord.ui.View | None = None,
) -> discord.Message:
    if interaction is not None:
        if interaction.response.is_done():
            return await interaction.followup.send(
                content=content, embed=embed, ephemeral=ephemeral, view=view
            )
        return await interaction.response.send_message(
            content=content, embed=embed, ephemeral=ephemeral, view=view
        )

    if ctx is None:
        raise ValueError("Either ctx or interaction must be provided")

    return await ctx.send(content=content, embed=embed, view=view)


async def defer_if_needed(interaction: discord.Interaction | None) -> None:
    if interaction is not None and not interaction.response.is_done():
        await interaction.response.defer(ephemeral=False)
