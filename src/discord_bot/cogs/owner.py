from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.checks import owner_only
from discord_bot.owner_dashboard import ServerPickerView
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


LOGGER = logging.getLogger("discord_bot.owner")


class OwnerCog(commands.Cog):
    """Entry point for the private, menu-driven OWNER control center."""

    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="owner",
        description="Ouvrir le centre de contrôle privé du bot.",
    )
    @owner_only()
    async def owner(self, interaction: discord.Interaction) -> None:
        await self.bot.wait_until_ready()
        guilds = list(self.bot.guilds)
        LOGGER.info(
            "Diagnostic temporaire /owner — bot.guilds : %d serveur(s) : %s",
            len(guilds),
            ", ".join(guild.name for guild in guilds) or "(aucun)",
        )
        guilds.sort(key=lambda guild: guild.name.casefold())
        if not guilds:
            await interaction.response.send_message(
                "Cette session Discord ne fournit aucun serveur à bot.guilds. "
                "Vérifiez que le bot de cette session est bien installé dans le serveur.",
                ephemeral=True,
            )
            return
        view = ServerPickerView(self.bot, guilds)
        await interaction.response.send_message(
            embed=view.embed(),
            view=view,
            ephemeral=True,
        )
