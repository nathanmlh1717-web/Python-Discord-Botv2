"""Discord slash-command bot."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.checks import (
    FeatureDisabledError,
    GuildCommandsDisabledError,
    GuildMaintenanceModeError,
    OwnerOnlyCheckFailure,
)
from discord_bot.cogs.core import CoreCog
from discord_bot.cogs.information import InformationCog
from discord_bot.cogs.logging import LoggingCog
from discord_bot.cogs.moderation import ModerationCog
from discord_bot.cogs.owner import OwnerCog
from discord_bot.cogs.setup import SetupCog
from discord_bot.cogs.utilities import UtilitiesCog
from discord_bot.common import COMMAND_FEATURES, feature_is_enabled, log_action
from discord_bot.storage import ActivityStore, GuildConfigStore, WarningStore
from discord_bot.views import TicketCloseView, TicketPanelView, VerifyView

LOGGER = logging.getLogger("discord_bot")


class OwnerAwareCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            return True
        bot = self.client
        config = await bot.config_store.get_guild(guild.id)
        command = interaction.command
        is_owner_command = command is not None and (
            command.name == "owner" or command.name.startswith("owner-")
        )
        if is_owner_command:
            return True
        if config.get("commands_disabled"):
            raise GuildCommandsDisabledError
        if config.get("maintenance_mode") and command is not None and command.name not in {"ping", "help"}:
            raise GuildMaintenanceModeError
        if command is not None:
            disabled_commands = config.get("disabled_commands", [])
            if isinstance(disabled_commands, list) and command.name in disabled_commands:
                raise FeatureDisabledError
            feature = COMMAND_FEATURES.get(command.name)
            if feature and not feature_is_enabled(config, feature):
                raise FeatureDisabledError
        return True


class SlashCommandBot(commands.Bot):
    """Bot that loads its features and restores persistent component views."""

    def __init__(self, owner_id: int) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
            tree_cls=OwnerAwareCommandTree,
        )
        self.owner_id = owner_id
        self.config_store = GuildConfigStore()
        self.warning_store = WarningStore()
        self.activity_store = ActivityStore()
        self.started_at = datetime.now(UTC)

    async def setup_hook(self) -> None:
        await self.config_store.load()
        await self.warning_store.load()
        await self.activity_store.load()

        for cog in (
            CoreCog(self),
            InformationCog(self),
            ModerationCog(self),
            UtilitiesCog(self),
            SetupCog(self),
            LoggingCog(self),
            OwnerCog(self),
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
        if isinstance(error, OwnerOnlyCheckFailure):
            message = "Cette commande est réservée au propriétaire configuré du bot."
        elif isinstance(error, GuildCommandsDisabledError):
            message = "Les commandes du bot sont désactivées sur ce serveur."
        elif isinstance(error, GuildMaintenanceModeError):
            message = "Le bot est en mode maintenance sur ce serveur. `/ping` et `/help` restent disponibles."
        elif isinstance(error, FeatureDisabledError):
            message = "Cette commande ou fonctionnalité est désactivée sur ce serveur."
        elif isinstance(error, app_commands.MissingPermissions):
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

        if interaction.guild is not None and isinstance(error, app_commands.CommandInvokeError):
            command_name = interaction.command.name if interaction.command else "inconnue"
            await self.activity_store.record_event(
                interaction.guild.id,
                "error",
                f"/{command_name}",
                actor_id=interaction.user.id,
                detail=str(error.original)[:500],
            )
            await self.notify_owner(
                "Erreur de commande",
                interaction.guild,
                f"/{command_name} · {type(error.original).__name__}: {str(error.original)[:300]}",
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            LOGGER.debug("Impossible d'envoyer le message d'erreur de commande.")

    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command[object, ..., object],
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        command_name = command.qualified_name
        await log_action(
            self,
            guild,
            f"/{command_name}",
            f"Commande utilisée par {interaction.user} (`{interaction.user.id}`).",
            category="commands",
            event_kind="command",
            actor_id=interaction.user.id,
        )
        if command_name.startswith("owner-") or command_name in {
            "ban",
            "kick",
            "timeout",
            "untimeout",
            "warn",
            "clear",
            "lock",
            "unlock",
            "ticketsetup",
            "verifysetup",
            "logsetup",
            "announce",
            "say",
            "embed",
        }:
            await self.notify_owner(
                "Fonction sensible utilisée",
                guild,
                f"/{command_name} · Utilisateur : {interaction.user} (`{interaction.user.id}`).",
            )

    async def notify_owner(
        self,
        title: str,
        guild: discord.Guild | None,
        detail: str,
    ) -> None:
        owner = self.get_user(self.owner_id)
        if owner is None:
            try:
                owner = await self.fetch_user(self.owner_id)
            except discord.HTTPException:
                LOGGER.warning("Impossible de récupérer le propriétaire pour l'audit OWNER.")
                return
        embed = discord.Embed(
            title=title[:256],
            description=detail[:3500],
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        if guild is not None:
            embed.add_field(name="Serveur", value=f"{guild.name}\n`{guild.id}`", inline=False)
        try:
            await owner.send(embed=embed)
        except discord.HTTPException:
            LOGGER.warning("Impossible d'envoyer une notification OWNER privée.")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.activity_store.record_event(
            guild.id,
            "server",
            "Bot ajouté au serveur",
            detail=f"{guild.name} (`{guild.id}`)",
        )
        await self.notify_owner(
            "Bot ajouté à un serveur",
            guild,
            f"Nom : **{guild.name}**\nID : `{guild.id}`\nMembres : {guild.member_count or 'inconnu'}",
        )

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.notify_owner(
            "Bot retiré d'un serveur",
            guild,
            f"Nom : **{guild.name}**\nID : `{guild.id}`",
        )


async def _run_bot(token: str, owner_id: int) -> None:
    bot = SlashCommandBot(owner_id)
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
    owner_value = os.getenv("OWNER_ID", "").strip()
    if not owner_value.isascii() or not owner_value.isdecimal() or len(owner_value) > 20:
        raise SystemExit(
            "OWNER_ID doit contenir l'identifiant numérique de l'utilisateur Discord propriétaire."
        )
    owner_id = int(owner_value)
    if owner_id <= 0:
        raise SystemExit("OWNER_ID doit être un identifiant Discord valide.")
    asyncio.run(_run_bot(token, owner_id))
