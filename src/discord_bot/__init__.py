"""Discord slash-command bot."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.cogs.core import CoreCog
from discord_bot.cogs.information import InformationCog
from discord_bot.cogs.logging import LoggingCog
from discord_bot.cogs.moderation import ModerationCog
from discord_bot.cogs.setup import SetupCog
from discord_bot.cogs.utilities import UtilitiesCog
from discord_bot.storage import GuildConfigStore, WarningStore
from discord_bot.views import TicketCloseView, TicketPanelView, VerifyView

LOGGER = logging.getLogger("discord_bot")


class SlashCommandBot(commands.Bot):
    """Bot that loads its features and restores persistent component views."""

    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
        )
        self.config_store = GuildConfigStore()
        self.warning_store = WarningStore()
        self.started_at = datetime.now(UTC)

    async def setup_hook(self) -> None:
        await self.config_store.load()
        await self.warning_store.load()

        for cog in (
            CoreCog(self),
            InformationCog(self),
            ModerationCog(self),
            UtilitiesCog(self),
            SetupCog(self),
            LoggingCog(self),
        ):
            await self.add_cog(cog)

        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        for guild_config in await self.config_store.all_guilds():
            role_ids = guild_config.get("verification_role_ids", [])
            if not isinstance(role_ids, list):
                role_ids = []
            current_role_id = guild_config.get("verification_role_id")
            if current_role_id:
                role_ids = [*role_ids, current_role_id]
            for role_id in {int(value) for value in role_ids if str(value).isdigit()}:
                self.add_view(VerifyView(role_id))

        synced_commands = await self.tree.sync()
        LOGGER.info("Commandes slash synchronisées : %d.", len(synced_commands))

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "Vous n'avez pas les permissions Discord nécessaires pour cette commande."
        elif isinstance(error, app_commands.BotMissingPermissions):
            message = "Le bot n'a pas les permissions Discord nécessaires pour effectuer cette action."
        elif isinstance(error, app_commands.CheckFailure):
            message = "Vous ne pouvez pas utiliser cette commande ici ou avec vos permissions actuelles."
        elif isinstance(error, app_commands.CommandInvokeError):
            cause = error.original
            if isinstance(cause, discord.Forbidden):
                message = "Discord a refusé l'action. Vérifiez les permissions et la hiérarchie des rôles du bot."
            elif isinstance(cause, discord.NotFound):
                message = "La ressource demandée n'existe plus sur ce serveur."
            elif isinstance(cause, discord.HTTPException):
                LOGGER.warning("Échec de commande Discord : %s", cause)
                message = "Discord n'a pas pu terminer l'action. Veuillez réessayer."
            else:
                LOGGER.exception(
                    "Erreur inattendue dans une commande slash.",
                    exc_info=(type(cause), cause, cause.__traceback__),
                )
                message = "Une erreur inattendue est survenue. Réessayez plus tard."
        else:
            LOGGER.error("Erreur de commande slash : %s", error)
            message = "La commande n'a pas pu être exécutée."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            LOGGER.debug("Impossible d'envoyer le message d'erreur de commande.")


async def _run_bot(token: str) -> None:
    bot = SlashCommandBot()
    async with bot:
        await bot.start(token)


def main() -> None:
    """Start the bot using the DISCORD_TOKEN environment variable."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(
            "DISCORD_TOKEN n'est pas défini. Ajoutez-le aux Secrets Replit avant de démarrer le bot."
        )
    asyncio.run(_run_bot(token))
