from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.checks import owner_only
from discord_bot.common import UNSAFE_VERIFICATION_PERMISSIONS

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


FEATURE_SETTINGS: dict[str, dict[str, tuple[str, str]]] = {
    "logs": {"salon": ("log_channel_id", "channel")},
    "tickets": {
        "role_staff": ("staff_role_id", "role"),
        "categorie": ("ticket_category_id", "category"),
    },
    "verification": {"role": ("verification_role_id", "verification_role")},
    "suggestions": {"salon": ("suggestion_channel_id", "channel")},
    "welcome": {"salon": ("welcome_channel_id", "channel")},
}
FEATURE_LABELS = {
    "logs": "Journaux",
    "tickets": "Tickets",
    "verification": "Vérification",
    "suggestions": "Suggestions",
    "welcome": "Bienvenue",
}
CONFIG_ACTIONS = [
    app_commands.Choice(name="Consulter", value="view"),
    app_commands.Choice(name="Modifier", value="set"),
    app_commands.Choice(name="Supprimer un réglage", value="delete"),
    app_commands.Choice(name="Réinitialiser cette fonction", value="reset"),
]
CONFIG_FEATURES = [
    app_commands.Choice(name=label, value=value)
    for value, label in FEATURE_LABELS.items()
]
OWNER_CONFIG_KEYS = {
    key
    for settings in FEATURE_SETTINGS.values()
    for key, _resource_type in settings.values()
}

def parse_snowflake(value: str) -> int | None:
    cleaned = value.strip()
    if not re.fullmatch(r"[0-9]{1,20}", cleaned):
        return None
    parsed = int(cleaned)
    return parsed if parsed > 0 else None


class OwnerCog(commands.Cog):
    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    def _get_guild(self, server_id: str) -> discord.Guild | None:
        parsed = parse_snowflake(server_id)
        return self.bot.get_guild(parsed) if parsed is not None else None

    async def _owner_name(self, guild: discord.Guild) -> str:
        if guild.owner is not None:
            return str(guild.owner)
        try:
            return str(await self.bot.fetch_user(guild.owner_id))
        except discord.HTTPException:
            return f"ID {guild.owner_id}"

    @app_commands.command(
        name="owner-servers",
        description="Lister les serveurs où se trouve le bot.",
    )
    @owner_only()
    async def owner_servers(self, interaction: discord.Interaction) -> None:
        if not self.bot.guilds:
            await interaction.response.send_message(
                "Le bot n'est présent sur aucun serveur.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        guilds = sorted(self.bot.guilds, key=lambda guild: guild.name.casefold())
        page_size = 12
        page_count = (len(guilds) + page_size - 1) // page_size
        for page_index in range(page_count):
            page_guilds = guilds[page_index * page_size : (page_index + 1) * page_size]
            embed = discord.Embed(
                title="Serveurs du bot",
                description=f"{len(guilds)} serveur(s) · page {page_index + 1}/{page_count}",
                color=discord.Color.blurple(),
            )
            for guild in page_guilds:
                member_count = guild.member_count if guild.member_count is not None else "inconnu"
                owner_name = await self._owner_name(guild)
                embed.add_field(
                    name=f"{guild.name[:180]}",
                    value=(
                        f"ID : `{guild.id}`\n"
                        f"Membres : **{member_count}**\n"
                        f"Propriétaire : {owner_name[:100]}"
                    ),
                    inline=False,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="owner-serverinfo",
        description="Afficher les informations accessibles sur un serveur du bot.",
    )
    @app_commands.describe(server_id="ID du serveur où se trouve le bot")
    @owner_only()
    async def owner_serverinfo(
        self,
        interaction: discord.Interaction,
        server_id: str,
    ) -> None:
        guild = self._get_guild(server_id)
        if guild is None:
            await interaction.response.send_message(
                "Serveur introuvable ou le bot n'y est pas installé. Vérifiez l'ID du serveur.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        bot_member = guild.me
        visible_channels: list[str] = []
        if bot_member is not None:
            visible_channels = [
                f"#{channel.name}"
                for channel in guild.text_channels
                if channel.permissions_for(bot_member).view_channel
            ]
        features = [feature.replace("_", " ").title() for feature in guild.features]
        embed = discord.Embed(
            title=f"Informations du serveur · {guild.name}",
            color=discord.Color.blurple(),
            timestamp=guild.created_at,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(
            name="Membres",
            value=str(guild.member_count if guild.member_count is not None else "Inconnu"),
            inline=True,
        )
        embed.add_field(name="Propriétaire", value=(await self._owner_name(guild))[:100], inline=True)
        embed.add_field(
            name="Créé le",
            value=discord.utils.format_dt(guild.created_at, style="D"),
            inline=True,
        )
        embed.add_field(name="Niveau de boost", value=str(guild.premium_tier), inline=True)
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count or 0), inline=True)
        embed.add_field(
            name=f"Salons textuels visibles par le bot ({len(visible_channels)})",
            value=", ".join(visible_channels[:30])[:1024] or "Aucun salon textuel accessible.",
            inline=False,
        )
        embed.add_field(
            name="Fonctionnalités du serveur",
            value=", ".join(features[:20])[:1024] or "Aucune fonctionnalité listée.",
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="owner-send",
        description="Envoyer un message ou un embed dans un salon accessible au bot.",
    )
    @app_commands.describe(
        server_id="ID du serveur où le bot est installé",
        channel_id="ID d'un salon textuel accessible au bot",
        message="Message à envoyer (facultatif si vous créez un embed)",
        embed_title="Titre de l'embed",
        embed_description="Texte de l'embed",
    )
    @owner_only()
    async def owner_send(
        self,
        interaction: discord.Interaction,
        server_id: str,
        channel_id: str,
        message: str | None = None,
        embed_title: str | None = None,
        embed_description: str | None = None,
    ) -> None:
        guild = self._get_guild(server_id)
        parsed_channel_id = parse_snowflake(channel_id)
        if guild is None or parsed_channel_id is None:
            await interaction.response.send_message(
                "Serveur ou salon introuvable. Vérifiez les deux identifiants.",
                ephemeral=True,
            )
            return
        if bool(message and message.strip()) == bool(embed_title or embed_description):
            await interaction.response.send_message(
                "Choisissez soit un message, soit un embed avec un titre et une description.",
                ephemeral=True,
            )
            return
        if embed_title is not None and not embed_description:
            await interaction.response.send_message(
                "La description est obligatoire pour créer un embed.",
                ephemeral=True,
            )
            return
        if embed_description is not None and not embed_title:
            await interaction.response.send_message(
                "Le titre est obligatoire pour créer un embed.",
                ephemeral=True,
            )
            return
        if message and len(message) > 2000:
            await interaction.response.send_message(
                "Un message Discord ne peut pas dépasser 2 000 caractères.",
                ephemeral=True,
            )
            return
        if embed_title and (len(embed_title) > 256 or len(embed_title) == 0):
            await interaction.response.send_message(
                "Le titre de l'embed doit contenir de 1 à 256 caractères.",
                ephemeral=True,
            )
            return
        if embed_description and (len(embed_description) > 4000 or len(embed_description) == 0):
            await interaction.response.send_message(
                "La description de l'embed doit contenir de 1 à 4 000 caractères.",
                ephemeral=True,
            )
            return

        channel = guild.get_channel_or_thread(parsed_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Le salon est introuvable ou n'est pas un salon textuel du serveur choisi.",
                ephemeral=True,
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "Impossible de vérifier les permissions du bot dans ce serveur.",
                ephemeral=True,
            )
            return
        permissions = channel.permissions_for(bot_member)
        can_send = (
            permissions.send_messages_in_threads
            if isinstance(channel, discord.Thread)
            else permissions.send_messages
        )
        if not permissions.view_channel or not can_send:
            await interaction.response.send_message(
                "Le bot n'a pas accès à ce salon ou n'y a pas la permission d'envoyer des messages.",
                ephemeral=True,
            )
            return
        if embed_title and not permissions.embed_links:
            await interaction.response.send_message(
                "Le bot n'a pas la permission d'intégrer des liens dans ce salon.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        if message and message.strip():
            await channel.send(
                message,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            embed = discord.Embed(
                title=embed_title,
                description=embed_description,
                color=discord.Color.blurple(),
            )
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        await interaction.followup.send(
            f"Message envoyé dans le serveur **{guild.name}**, salon {channel.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="owner-config",
        description="Consulter ou modifier uniquement les réglages des fonctionnalités du bot.",
    )
    @app_commands.describe(
        server_id="ID du serveur où le bot est installé",
        action="Consulter, modifier ou réinitialiser un réglage du bot",
        feature="Fonctionnalité dont vous voulez gérer les réglages",
        setting="Réglage : salon, role_staff, categorie ou role",
        value="ID Discord du salon, de la catégorie ou du rôle",
    )
    @app_commands.choices(action=CONFIG_ACTIONS, feature=CONFIG_FEATURES)
    @owner_only()
    async def owner_config(
        self,
        interaction: discord.Interaction,
        server_id: str,
        action: app_commands.Choice[str],
        feature: app_commands.Choice[str],
        setting: str | None = None,
        value: str | None = None,
    ) -> None:
        guild = self._get_guild(server_id)
        if guild is None:
            await interaction.response.send_message(
                "Serveur introuvable ou le bot n'y est pas installé.",
                ephemeral=True,
            )
            return
        feature_key = feature.value
        settings = FEATURE_SETTINGS[feature_key]
        config = await self.bot.config_store.get_guild(guild.id)

        if action.value == "view":
            if setting and setting not in settings:
                await interaction.response.send_message(
                    "Ce réglage n'existe pas pour cette fonctionnalité.",
                    ephemeral=True,
                )
                return
            selected = {setting: settings[setting]} if setting else settings
            embed = discord.Embed(
                title=f"Configuration · {FEATURE_LABELS[feature_key]} · {guild.name}",
                color=discord.Color.blurple(),
            )
            for label, (config_key, _resource_type) in selected.items():
                stored_value = config.get(config_key)
                embed.add_field(
                    name=label,
                    value=self._format_config_value(guild, config_key, stored_value),
                    inline=False,
                )
            if feature_key == "verification":
                embed.add_field(
                    name="Panneaux de vérification précédents",
                    value=str(max(0, len(config.get("verification_role_ids", [])) - 1)),
                    inline=False,
                )
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )
            return

        if action.value == "reset":
            keys = [key for key, _kind in settings.values()]
            if feature_key == "verification":
                keys.append("verification_role_ids")
            await self.bot.config_store.remove_guild_values(guild.id, *keys)
            await interaction.response.send_message(
                f"Les réglages de **{FEATURE_LABELS[feature_key]}** ont été réinitialisés pour **{guild.name}**.",
                ephemeral=True,
            )
            return

        if not setting or setting not in settings:
            await interaction.response.send_message(
                "Indiquez un réglage valide pour cette fonctionnalité.",
                ephemeral=True,
            )
            return
        config_key, resource_type = settings[setting]

        if action.value == "delete":
            keys = [config_key]
            if config_key == "verification_role_id":
                keys.append("verification_role_ids")
            await self.bot.config_store.remove_guild_values(guild.id, *keys)
            await interaction.response.send_message(
                f"Le réglage `{setting}` a été supprimé pour **{guild.name}**.",
                ephemeral=True,
            )
            return

        if action.value != "set" or not value:
            await interaction.response.send_message(
                "Pour modifier un réglage, indiquez son nouvel ID Discord.",
                ephemeral=True,
            )
            return
        resource_id = parse_snowflake(value)
        if resource_id is None:
            await interaction.response.send_message(
                "L'identifiant doit être un ID Discord numérique valide.",
                ephemeral=True,
            )
            return

        bot_member = guild.me
        if resource_type in {"role", "verification_role"}:
            role = guild.get_role(resource_id)
            if role is None or bot_member is None:
                await interaction.response.send_message(
                    "Ce rôle est introuvable sur le serveur.",
                    ephemeral=True,
                )
                return
            if resource_type == "verification_role":
                if role.is_default() or role.managed or role >= bot_member.top_role:
                    await interaction.response.send_message(
                        "Le rôle de vérification doit être attribuable et inférieur au rôle le plus élevé du bot.",
                        ephemeral=True,
                    )
                    return
                if any(
                    getattr(role.permissions, permission)
                    for permission in UNSAFE_VERIFICATION_PERMISSIONS
                ):
                    await interaction.response.send_message(
                        "Ce rôle possède des permissions sensibles et ne peut pas être attribué par la vérification.",
                        ephemeral=True,
                    )
                    return
            elif role.is_default() or role >= bot_member.top_role:
                await interaction.response.send_message(
                    "Le rôle staff doit être inférieur au rôle le plus élevé du bot.",
                    ephemeral=True,
                )
                return
            new_values: dict[str, object] = {config_key: role.id}
            if config_key == "verification_role_id":
                previous_ids = config.get("verification_role_ids", [])
                if not isinstance(previous_ids, list):
                    previous_ids = []
                new_values["verification_role_ids"] = sorted(
                    {int(item) for item in previous_ids if str(item).isdigit()} | {role.id}
                )
            await self.bot.config_store.set_guild_values(guild.id, **new_values)
            if config_key == "verification_role_id":
                from discord_bot.views import VerifyView

                self.bot.add_view(VerifyView(role.id))
        else:
            resource = guild.get_channel(resource_id)
            correct_type = (
                isinstance(resource, discord.CategoryChannel)
                if resource_type == "category"
                else isinstance(resource, discord.TextChannel)
            )
            if not correct_type or bot_member is None:
                await interaction.response.send_message(
                    "Le salon ou la catégorie est introuvable dans ce serveur, ou son type ne convient pas.",
                    ephemeral=True,
                )
                return
            permissions = resource.permissions_for(bot_member)
            if not permissions.view_channel:
                await interaction.response.send_message(
                    "Le bot ne peut pas accéder à ce salon ou à cette catégorie.",
                    ephemeral=True,
                )
                return
            if resource_type == "channel" and (
                not permissions.send_messages or not permissions.embed_links
            ):
                await interaction.response.send_message(
                    "Le bot doit pouvoir voir ce salon, y envoyer des messages et y intégrer des liens.",
                    ephemeral=True,
                )
                return
            if resource_type == "channel" and config_key == "suggestion_channel_id" and not permissions.add_reactions:
                await interaction.response.send_message(
                    "Le bot doit pouvoir ajouter des réactions dans le salon de suggestions.",
                    ephemeral=True,
                )
                return
            if resource_type == "category" and not bot_member.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "Le bot doit disposer de la permission `Gérer les salons` pour utiliser cette catégorie de tickets.",
                    ephemeral=True,
                )
                return
            await self.bot.config_store.set_guild_values(guild.id, **{config_key: resource_id})

        await interaction.response.send_message(
            f"Le réglage **{setting}** a été modifié pour **{guild.name}**.",
            ephemeral=True,
        )

    def _format_config_value(
        self,
        guild: discord.Guild,
        key: str,
        value: object,
    ) -> str:
        if not value:
            return "Non configuré"
        parsed = int(value)
        if key.endswith("_role_id"):
            role = guild.get_role(parsed)
            return role.mention if role else f"Rôle supprimé (`{parsed}`)"
        channel = guild.get_channel(parsed)
        if channel:
            return channel.mention
        return f"Salon supprimé ou inaccessible (`{parsed}`)"

    @app_commands.command(
        name="owner-leave",
        description="Faire quitter au bot un serveur après confirmation.",
    )
    @app_commands.describe(
        server_id="ID du serveur que le bot doit quitter",
        confirm="Confirmer le départ du bot de ce serveur",
    )
    @owner_only()
    async def owner_leave(
        self,
        interaction: discord.Interaction,
        server_id: str,
        confirm: bool,
    ) -> None:
        guild = self._get_guild(server_id)
        if guild is None:
            await interaction.response.send_message(
                "Serveur introuvable ou le bot n'y est pas installé.",
                ephemeral=True,
            )
            return
        if not confirm:
            await interaction.response.send_message(
                f"Départ annulé. Relancez la commande avec `confirm: true` pour quitter **{guild.name}**.",
                ephemeral=True,
            )
            return
        name = guild.name
        await interaction.response.defer(ephemeral=True, thinking=True)
        await guild.leave()
        await interaction.followup.send(
            f"Le bot a quitté **{name}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="owner-disable",
        description="Désactiver les commandes du bot sur un serveur.",
    )
    @app_commands.describe(server_id="ID du serveur à désactiver")
    @owner_only()
    async def owner_disable(
        self,
        interaction: discord.Interaction,
        server_id: str,
    ) -> None:
        guild = self._get_guild(server_id)
        if guild is None:
            await interaction.response.send_message(
                "Serveur introuvable ou le bot n'y est pas installé.",
                ephemeral=True,
            )
            return
        await self.bot.config_store.set_guild_values(
            guild.id,
            commands_disabled=True,
        )
        await interaction.response.send_message(
            f"Les commandes sont désactivées pour **{guild.name}**. Le propriétaire peut toujours utiliser `/owner-enable`.",
            ephemeral=True,
        )

    @app_commands.command(
        name="owner-enable",
        description="Réactiver les commandes du bot sur un serveur.",
    )
    @app_commands.describe(server_id="ID du serveur à réactiver")
    @owner_only()
    async def owner_enable(
        self,
        interaction: discord.Interaction,
        server_id: str,
    ) -> None:
        guild = self._get_guild(server_id)
        if guild is None:
            await interaction.response.send_message(
                "Serveur introuvable ou le bot n'y est pas installé.",
                ephemeral=True,
            )
            return
        await self.bot.config_store.remove_guild_values(
            guild.id,
            "commands_disabled",
        )
        await interaction.response.send_message(
            f"Les commandes sont réactivées pour **{guild.name}**.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        owner = self.bot.get_user(self.bot.owner_id)
        if owner is None:
            try:
                owner = await self.bot.fetch_user(self.bot.owner_id)
            except discord.HTTPException:
                return
        embed = discord.Embed(
            title="Nouveau serveur",
            description=(
                f"Le bot a rejoint **{guild.name}**.\n"
                f"ID : `{guild.id}`\n"
                f"Membres : {guild.member_count if guild.member_count is not None else 'inconnu'}"
            ),
            color=discord.Color.green(),
        )
        try:
            await owner.send(embed=embed)
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass
