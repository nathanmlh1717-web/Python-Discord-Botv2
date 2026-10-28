from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.common import (
    command_reason,
    format_member,
    log_action,
    normalize_reason,
    parse_timeout_duration,
    target_hierarchy_error,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


class ModerationCog(commands.Cog):
    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    @app_commands.command(name="ban", description="Bannir un membre avec une raison.")
    @app_commands.describe(member="Membre à bannir", reason="Raison du bannissement")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        reason = normalize_reason(reason) or ""
        if not reason:
            await interaction.response.send_message(
                "La raison est obligatoire et ne peut pas dépasser 500 caractères.",
                ephemeral=True,
            )
            return
        error = target_hierarchy_error(interaction, member)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        guild = interaction.guild
        assert guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        await member.ban(reason=command_reason(reason, interaction.user), delete_message_seconds=0)
        await log_action(
            self.bot,
            guild,
            "Membre banni",
            f"Membre : {format_member(member)}\nModérateur : {interaction.user.mention}\nRaison : {reason}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(
            f"{member.mention} a été banni. Raison : {reason}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="kick", description="Expulser un membre du serveur.")
    @app_commands.describe(member="Membre à expulser", reason="Raison de l'expulsion")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        reason = normalize_reason(reason) or ""
        if not reason:
            await interaction.response.send_message(
                "La raison est obligatoire et ne peut pas dépasser 500 caractères.",
                ephemeral=True,
            )
            return
        error = target_hierarchy_error(interaction, member)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        guild = interaction.guild
        assert guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        await member.kick(reason=command_reason(reason, interaction.user))
        await log_action(
            self.bot,
            guild,
            "Membre expulsé",
            f"Membre : {format_member(member)}\nModérateur : {interaction.user.mention}\nRaison : {reason}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(
            f"{member.mention} a été expulsé. Raison : {reason}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="timeout", description="Mettre un membre en timeout.")
    @app_commands.describe(
        member="Membre à mettre en timeout",
        duration="Durée : 15m, 2h, 3d ou 1w (maximum 28 jours)",
        reason="Raison du timeout",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str,
    ) -> None:
        reason = normalize_reason(reason) or ""
        if not reason:
            await interaction.response.send_message(
                "La raison est obligatoire et ne peut pas dépasser 500 caractères.",
                ephemeral=True,
            )
            return
        parsed_duration = parse_timeout_duration(duration)
        if parsed_duration is None:
            await interaction.response.send_message(
                "Durée invalide. Utilisez par exemple `15m`, `2h`, `3d` ou `1w` (de 1 minute à 28 jours).",
                ephemeral=True,
            )
            return
        error = target_hierarchy_error(interaction, member)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        guild = interaction.guild
        assert guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        await member.timeout(parsed_duration, reason=command_reason(reason, interaction.user))
        expiration = discord.utils.format_dt(discord.utils.utcnow() + parsed_duration, style="R")
        await log_action(
            self.bot,
            guild,
            "Timeout appliqué",
            f"Membre : {format_member(member)}\nModérateur : {interaction.user.mention}\n"
            f"Durée : {duration}\nFin : {expiration}\nRaison : {reason}",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(
            f"{member.mention} est en timeout pour {duration} (jusqu'à {expiration}).",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="untimeout", description="Retirer le timeout d'un membre.")
    @app_commands.describe(member="Membre à rétablir", reason="Raison du retrait")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        reason = normalize_reason(reason) or ""
        if not reason:
            await interaction.response.send_message(
                "La raison est obligatoire et ne peut pas dépasser 500 caractères.",
                ephemeral=True,
            )
            return
        error = target_hierarchy_error(interaction, member)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        guild = interaction.guild
        assert guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        await member.timeout(None, reason=command_reason(reason, interaction.user))
        await log_action(
            self.bot,
            guild,
            "Timeout retiré",
            f"Membre : {format_member(member)}\nModérateur : {interaction.user.mention}\nRaison : {reason}",
            color=discord.Color.green(),
        )
        await interaction.followup.send(
            f"Le timeout de {member.mention} a été retiré.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="warn", description="Avertir un membre et enregistrer l'avertissement.")
    @app_commands.describe(member="Membre à avertir", reason="Raison de l'avertissement")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        reason = normalize_reason(reason) or ""
        if not reason:
            await interaction.response.send_message(
                "La raison est obligatoire et ne peut pas dépasser 500 caractères.",
                ephemeral=True,
            )
            return
        error = target_hierarchy_error(interaction, member)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        guild = interaction.guild
        assert guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        warning_count = await self.bot.warning_store.add_warning(
            guild.id,
            member.id,
            interaction.user.id,
            reason.strip(),
        )
        await log_action(
            self.bot,
            guild,
            "Avertissement ajouté",
            f"Membre : {format_member(member)}\nModérateur : {interaction.user.mention}\n"
            f"Total : {warning_count}\nRaison : {reason}",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(
            f"{member.mention} a reçu un avertissement (total : {warning_count}). Raison : {reason}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="warnings", description="Afficher les avertissements d'un membre.")
    @app_commands.describe(member="Membre dont vous voulez consulter les avertissements")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return
        records = await self.bot.warning_store.get_warnings(guild.id, member.id)
        if not records:
            await interaction.response.send_message(
                f"{member.display_name} n'a aucun avertissement enregistré.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Avertissements de {member.display_name}",
            description=f"Total : **{len(records)}** · affichage des 10 plus récents",
            color=discord.Color.orange(),
        )
        for index, record in enumerate(reversed(records[-10:]), start=1):
            created_at = record.get("created_at", "")
            try:
                timestamp = discord.utils.format_dt(datetime.fromisoformat(created_at), style="R")
            except (TypeError, ValueError):
                timestamp = "date inconnue"
            reason = str(record.get("reason", "Aucune raison fournie."))[:700]
            moderator_id = record.get("moderator_id", "inconnu")
            embed.add_field(
                name=f"#{len(records) - index + 1} · {timestamp}",
                value=f"Par <@{moderator_id}> — {reason}",
                inline=False,
            )
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="clear", description="Supprimer des messages récents du salon.")
    @app_commands.describe(count="Nombre de messages à supprimer (1 à 100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def clear(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 100],
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Cette commande ne peut pas être utilisée dans ce type de salon.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        deleted = await channel.purge(
            limit=count,
            reason=f"Suppression par {interaction.user} ({interaction.user.id})",
        )
        if interaction.guild is not None:
            await log_action(
                self.bot,
                interaction.guild,
                "Messages supprimés",
                f"Modérateur : {interaction.user.mention}\nSalon : {channel.mention}\n"
                f"Nombre supprimé : **{len(deleted)}**",
                color=discord.Color.orange(),
            )
        await interaction.followup.send(
            f"**{len(deleted)}** message(s) supprimé(s).",
            ephemeral=True,
        )

    @app_commands.command(name="slowmode", description="Modifier le mode lent du salon.")
    @app_commands.describe(seconds="Délai en secondes (0 à 21 600)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel classique.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await channel.edit(
            slowmode_delay=seconds,
            reason=f"Mode lent modifié par {interaction.user} ({interaction.user.id})",
        )
        value = "désactivé" if seconds == 0 else f"réglé sur **{seconds} seconde(s)**"
        await interaction.followup.send(f"Le mode lent est {value}.", ephemeral=True)

    @app_commands.command(name="lock", description="Verrouiller le salon pour @everyone.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel de serveur.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await channel.set_permissions(
            guild.default_role,
            send_messages=False,
            reason=f"Salon verrouillé par {interaction.user} ({interaction.user.id})",
        )
        await interaction.followup.send(
            f"🔒 {channel.mention} est verrouillé pour @everyone.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="unlock", description="Déverrouiller le salon pour @everyone.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel de serveur.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await channel.set_permissions(
            guild.default_role,
            send_messages=None,
            reason=f"Salon déverrouillé par {interaction.user} ({interaction.user.id})",
        )
        await interaction.followup.send(
            f"🔓 {channel.mention} est déverrouillé.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
