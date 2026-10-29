"""Shared OWNER authorization and audit helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


async def require_owner(interaction: discord.Interaction, bot: SlashCommandBot) -> bool:
    """Recheck the configured owner ID for every panel or modal interaction."""
    if interaction.user.id == bot.owner_id:
        return True
    message = "Ce panneau est réservé au propriétaire du bot."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    return False


async def audit_owner_action(
    bot: SlashCommandBot,
    guild: discord.Guild,
    action: str,
    detail: str,
) -> None:
    await bot.activity_store.record_event(
        guild.id,
        "owner",
        action,
        actor_id=bot.owner_id,
        detail=detail,
    )
    await bot.notify_owner(
        "Action du centre OWNER",
        guild,
        f"Action : **{action}**\n{detail}",
    )


class OwnerOnlyView(discord.ui.View):
    def __init__(self, bot: SlashCommandBot, *, timeout: float = 600) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.owner_id = bot.owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await require_owner(interaction, self.bot)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        if interaction.guild is not None:
            await self.bot.notify_owner(
                "Erreur dans le centre OWNER",
                interaction.guild,
                f"Composant : {type(item).__name__}\n"
                f"Exception : {type(error).__name__}",
            )
        message = "Une erreur est survenue dans le panneau. Réessayez."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
