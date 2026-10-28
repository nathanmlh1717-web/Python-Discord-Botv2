"""Ephemeral, owner-only control panel for the bot's guild features."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common import (
    COMMAND_FEATURES,
    feature_is_enabled,
    log_action,
    parse_timeout_duration,
    verification_role_error,
)
from discord_bot.views import (
    OWNER_RE,
    STATUS_RE,
    TicketPanelView,
    VerifyView,
)

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


FEATURE_LABELS = {
    "moderation": "Modération",
    "tickets": "Tickets",
    "utilities": "Utilitaires",
    "suggestions": "Suggestions",
    "verification": "Vérification",
    "logs": "Logs",
    "information": "Informations",
}
FEATURE_DESCRIPTIONS = {
    "moderation": "Commandes de modération et sanctions.",
    "tickets": "Panneaux, création et gestion des tickets.",
    "utilities": "Messages, sondages, annonces et signalements.",
    "suggestions": "Publication et vote des suggestions.",
    "verification": "Panneaux et attribution du rôle de vérification.",
    "logs": "Journalisation des événements dans le salon configuré.",
    "information": "Commandes d'information et de latence.",
}
LOG_CATEGORIES = {
    "moderation": "Modération",
    "tickets": "Tickets",
    "messages": "Suppressions de messages",
    "commands": "Utilisation des commandes",
    "welcome": "Bienvenue",
}
TEXT_CHANNEL_TYPES = [discord.ChannelType.text, discord.ChannelType.news]


async def require_owner(
    interaction: discord.Interaction,
    bot: SlashCommandBot,
) -> bool:
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


def _permission_lines(guild: discord.Guild) -> str:
    bot_member = guild.me
    if bot_member is None:
        return "État des permissions indisponible."
    permissions = bot_member.guild_permissions
    checks = (
        ("Voir les salons", permissions.view_channel),
        ("Envoyer des messages", permissions.send_messages),
        ("Intégrer des liens", permissions.embed_links),
        ("Gérer les salons", permissions.manage_channels),
        ("Gérer les rôles", permissions.manage_roles),
        ("Bannir", permissions.ban_members),
        ("Expulser", permissions.kick_members),
        ("Timeout", permissions.moderate_members),
        ("Gérer les messages", permissions.manage_messages),
        ("Ajouter des réactions", permissions.add_reactions),
    )
    return "\n".join(
        f"{'✅' if granted else '—'} {label}"
        for label, granted in checks
    )


class OwnerOnlyView(discord.ui.View):
    def __init__(self, bot: SlashCommandBot, *, timeout: float = 600) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.owner_id = bot.owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await require_owner(interaction, self.bot)


class GuildPickerSelect(discord.ui.Select):
    def __init__(self, view: ServerPickerView, guilds: list[discord.Guild]) -> None:
        options = [
            discord.SelectOption(
                label=guild.name[:100],
                value=str(guild.id),
                description=(
                    f"{guild.member_count or 'Membres inconnus'} membres"
                    if guild.member_count is not None
                    else "Membres inconnus"
                )[:100],
            )
            for guild in guilds[:25]
        ]
        super().__init__(
            placeholder="Choisir un serveur…",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.panel = view

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        await self.panel.open_guild(interaction, int(self.values[0]))


class PickerPageButton(discord.ui.Button):
    def __init__(self, panel: ServerPickerView, delta: int) -> None:
        self.panel = panel
        self.delta = delta
        super().__init__(
            label="Précédent" if delta < 0 else "Suivant",
            emoji="◀️" if delta < 0 else "▶️",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        await self.panel.change_page(interaction, self.delta)


class ServerPickerView(OwnerOnlyView):
    def __init__(
        self,
        bot: SlashCommandBot,
        guilds: list[discord.Guild] | None = None,
        page: int = 0,
    ) -> None:
        super().__init__(bot)
        self.guilds = sorted(guilds or bot.guilds, key=lambda guild: guild.name.casefold())
        self.page = page
        self.page_count = max(1, (len(self.guilds) + 24) // 25)
        start = page * 25
        self.add_item(GuildPickerSelect(self, self.guilds[start : start + 25]))
        if self.page_count > 1:
            self.add_item(PickerPageButton(self, -1))
            self.add_item(PickerPageButton(self, 1))

    def embed(self) -> discord.Embed:
        return discord.Embed(
            title="Centre de contrôle OWNER",
            description=(
                f"Choisissez un serveur pour ouvrir son tableau de bord.\n"
                f"**{len(self.guilds)} serveur(s)** · page {self.page + 1}/{self.page_count}"
            ),
            color=discord.Color.blurple(),
        ).set_footer(text="Panneau privé · accès réservé au propriétaire du bot")

    async def change_page(self, interaction: discord.Interaction, delta: int) -> None:
        page = (self.page + delta) % self.page_count
        view = ServerPickerView(self.bot, self.guilds, page)
        await interaction.response.edit_message(embed=view.embed(), view=view)

    async def open_guild(self, interaction: discord.Interaction, guild_id: int) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await interaction.response.send_message(
                "Le bot n'est plus présent sur ce serveur.",
                ephemeral=True,
            )
            return
        view = OwnerDashboardView(self.bot, guild.id, "home")
        await interaction.response.edit_message(embed=await view.render(), view=view)


class DashboardButton(discord.ui.Button):
    def __init__(
        self,
        panel: OwnerDashboardView,
        label: str,
        emoji: str,
        section: str,
        row: int,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
    ) -> None:
        super().__init__(label=label, emoji=emoji, style=style, row=row)
        self.panel = panel
        self.section = section

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        await self.panel.navigate(interaction, self.section)


class DashboardActionSelect(discord.ui.Select):
    def __init__(
        self,
        panel: OwnerDashboardView,
        options: list[discord.SelectOption],
        placeholder: str,
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options[:25],
            row=4,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        await self.panel.handle_action(interaction, self.values[0])


class DashboardCommandSelect(discord.ui.Select):
    def __init__(self, panel: OwnerDashboardView) -> None:
        commands = sorted(
            (
                command
                for command in panel.bot.tree.get_commands()
                if command.name != "owner" and not command.name.startswith("owner-")
            ),
            key=lambda command: command.name,
        )
        self.panel = panel
        page_size = 22
        self.page_count = max(1, (len(commands) + page_size - 1) // page_size)
        page = panel.page % self.page_count
        page_commands = commands[page * page_size : (page + 1) * page_size]
        options = [
            discord.SelectOption(
                label=command.name[:100],
                value=command.name,
                description=command.description[:100] or "Commande slash",
            )
            for command in page_commands
        ]
        if page > 0:
            options.append(discord.SelectOption(label="Page précédente", value="__previous__"))
        if page + 1 < self.page_count:
            options.append(discord.SelectOption(label="Page suivante", value="__next__"))
        super().__init__(
            placeholder=f"Activer ou désactiver une commande · {page + 1}/{self.page_count}",
            min_values=1,
            max_values=1,
            options=options[:25],
            row=4,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        value = self.values[0]
        if value == "__next__":
            await self.panel.navigate(interaction, "commands", page=self.panel.page + 1)
        elif value == "__previous__":
            await self.panel.navigate(interaction, "commands", page=max(0, self.panel.page - 1))
        else:
            await self.panel.toggle_command(interaction, value)


class PanelChannelSelect(discord.ui.ChannelSelect):
    def __init__(
        self,
        panel: OwnerDashboardView,
        purpose: str,
        placeholder: str = "Choisir un salon…",
        channel_types: list[discord.ChannelType] | None = None,
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            channel_types=channel_types or TEXT_CHANNEL_TYPES,
            row=4,
        )
        self.panel = panel
        self.purpose = purpose

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        await self.panel.handle_channel(interaction, self.purpose, self.values[0])


class PanelRoleSelect(discord.ui.RoleSelect):
    def __init__(self, panel: OwnerDashboardView, purpose: str, placeholder: str) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            row=4,
        )
        self.panel = panel
        self.purpose = purpose

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        await self.panel.handle_role(interaction, self.purpose, self.values[0])


class PanelUserSelect(discord.ui.UserSelect):
    def __init__(self, panel: OwnerDashboardView) -> None:
        super().__init__(
            placeholder="Choisir un membre du serveur…",
            min_values=1,
            max_values=1,
            row=4,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        selected = self.values[0]
        view = OwnerDashboardView(
            self.panel.bot,
            self.panel.guild_id,
            "moderation",
            target_member_id=selected.id,
        )
        await interaction.response.edit_message(embed=await view.render(), view=view)


class TicketSelect(discord.ui.Select):
    def __init__(self, panel: OwnerDashboardView, channels: list[discord.TextChannel]) -> None:
        options = [
            discord.SelectOption(
                label=channel.name[:100],
                value=str(channel.id),
                description=(channel.topic or "Ticket ouvert")[:100],
            )
            for channel in channels[:25]
        ]
        super().__init__(
            placeholder="Choisir un ticket ouvert…",
            min_values=1,
            max_values=1,
            options=options or [discord.SelectOption(label="Aucun ticket ouvert", value="0")],
            disabled=not channels,
            row=4,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        if self.values[0] == "0":
            return
        view = OwnerDashboardView(
            self.panel.bot,
            self.panel.guild_id,
            "tickets",
            selected_ticket_id=int(self.values[0]),
        )
        await interaction.response.edit_message(embed=await view.render(), view=view)


class OwnerDashboardView(OwnerOnlyView):
    def __init__(
        self,
        bot: SlashCommandBot,
        guild_id: int,
        section: str = "home",
        *,
        target_member_id: int | None = None,
        selected_ticket_id: int | None = None,
        page: int = 0,
        input_mode: str | None = None,
    ) -> None:
        super().__init__(bot)
        self.guild_id = guild_id
        self.section = section
        self.target_member_id = target_member_id
        self.selected_ticket_id = selected_ticket_id
        self.page = page
        self.input_mode = input_mode
        self._add_navigation()
        self._add_section_control()

    def _add_navigation(self) -> None:
        tabs = (
            ("Accueil", "🏠", "home", 0),
            ("Fonctions", "⚙️", "features", 0),
            ("Commandes", "⌨️", "commands", 0),
            ("Modération", "🛡️", "moderation", 1),
            ("Tickets", "🎫", "tickets", 1),
            ("Messages", "💬", "messages", 1),
            ("Bienvenue", "👋", "welcome", 2),
            ("Vérification", "✅", "verification", 2),
            ("Logs", "📜", "logs", 2),
            ("Stats", "📊", "stats", 3),
            ("Contrôle", "🔒", "control", 3),
            ("Serveurs", "↩️", "picker", 3),
            ("Fermer", "✖️", "close", 3),
        )
        for label, emoji, section, row in tabs:
            style = discord.ButtonStyle.primary if self.section == section else discord.ButtonStyle.secondary
            self.add_item(DashboardButton(self, label, emoji, section, row, style))

    def _add_section_control(self) -> None:
        if self.input_mode:
            self._add_input_control()
            return
        options: list[discord.SelectOption] = []
        placeholder = "Choisir une action…"
        if self.section == "features":
            options = [
                discord.SelectOption(
                    label=f"Basculer : {label}",
                    value=f"feature:{key}",
                    description=FEATURE_DESCRIPTIONS[key],
                )
                for key, label in FEATURE_LABELS.items()
            ]
            placeholder = "Activer ou désactiver une fonctionnalité…"
        elif self.section == "commands":
            self.add_item(DashboardCommandSelect(self))
            return
        elif self.section == "moderation":
            if self.target_member_id is None:
                self.add_item(PanelUserSelect(self))
                return
            options = [
                discord.SelectOption(label="Voir les sanctions", value="moderation:warnings"),
                discord.SelectOption(label="Ajouter un avertissement", value="moderation:warn"),
                discord.SelectOption(label="Mettre en timeout", value="moderation:timeout"),
                discord.SelectOption(label="Expulser", value="moderation:kick"),
                discord.SelectOption(label="Bannir", value="moderation:ban"),
                discord.SelectOption(label="Retirer le dernier warn", value="moderation:remove_warn"),
            ]
            placeholder = "Action de modération…"
        elif self.section == "tickets":
            if self.selected_ticket_id is not None:
                options = [
                    discord.SelectOption(label="Fermer ce ticket", value="ticket:close"),
                    discord.SelectOption(label="Choisir un autre ticket", value="ticket:list"),
                ]
            else:
                options = [
                    discord.SelectOption(label="Activer / désactiver les tickets", value="feature:tickets"),
                    discord.SelectOption(label="Choisir le rôle staff", value="ticket:staff"),
                    discord.SelectOption(label="Choisir la catégorie", value="ticket:category"),
                    discord.SelectOption(label="Publier le panneau", value="ticket:panel"),
                    discord.SelectOption(label="Voir les tickets ouverts", value="ticket:list"),
                ]
            placeholder = "Gérer les tickets…"
        elif self.section == "messages":
            options = [
                discord.SelectOption(label="Choisir un salon", value="message:channel"),
                discord.SelectOption(label="Envoyer un message", value="message:send"),
                discord.SelectOption(label="Envoyer un embed", value="message:embed"),
                discord.SelectOption(label="Envoyer une annonce", value="message:announce"),
            ]
            placeholder = "Messages et annonces…"
        elif self.section == "welcome":
            options = [
                discord.SelectOption(label="Choisir le salon", value="welcome:channel"),
                discord.SelectOption(label="Modifier le message", value="welcome:message"),
                discord.SelectOption(label="Prévisualiser", value="welcome:preview"),
            ]
            placeholder = "Réglages de bienvenue…"
        elif self.section == "verification":
            options = [
                discord.SelectOption(label="Activer / désactiver", value="feature:verification"),
                discord.SelectOption(label="Choisir le rôle", value="verify:role"),
                discord.SelectOption(label="Choisir le salon du panneau", value="verify:channel"),
                discord.SelectOption(label="Envoyer le panneau", value="verify:publish"),
            ]
            placeholder = "Configurer la vérification…"
        elif self.section == "logs":
            options = [
                discord.SelectOption(label="Choisir le salon de logs", value="logs:channel"),
                discord.SelectOption(label="Activer / désactiver une catégorie", value="logs:categories"),
                discord.SelectOption(label="Voir les dernières actions", value="logs:recent"),
            ]
            placeholder = "Journaux du bot…"
        elif self.section == "stats":
            options = [
                discord.SelectOption(label="Voir les dernières actions", value="stats:recent"),
            ]
            placeholder = "Statistiques…"
        elif self.section == "control":
            options = [
                discord.SelectOption(label="Activer / désactiver les commandes", value="control:commands"),
                discord.SelectOption(label="Activer / désactiver la maintenance", value="control:maintenance"),
                discord.SelectOption(label="Réinitialiser la configuration", value="control:reset"),
                discord.SelectOption(label="Faire quitter le serveur", value="control:leave"),
            ]
            placeholder = "Contrôles du serveur…"
        if options:
            self.add_item(DashboardActionSelect(self, options, placeholder))

    def _add_input_control(self) -> None:
        mode = self.input_mode
        if mode == "ticket_staff":
            self.add_item(PanelRoleSelect(self, mode, "Choisir le rôle staff…"))
        elif mode == "verification_role":
            self.add_item(PanelRoleSelect(self, mode, "Choisir le rôle de vérification…"))
        elif mode == "ticket_category":
            self.add_item(
                PanelChannelSelect(
                    self,
                    mode,
                    "Choisir une catégorie…",
                    [discord.ChannelType.category],
                )
            )
        elif mode == "ticket_list":
            guild = self.guild()
            tickets = self._open_tickets(guild) if guild else []
            self.add_item(TicketSelect(self, tickets))
        else:
            labels = {
                "ticket_panel": "Choisir le salon du panneau…",
                "message_channel": "Choisir le salon de destination…",
                "welcome_channel": "Choisir le salon de bienvenue…",
                "verify_channel": "Choisir le salon du panneau…",
                "verify_publish": "Choisir le salon du panneau…",
                "log_channel": "Choisir le salon de logs…",
            }
            self.add_item(PanelChannelSelect(self, mode, labels.get(mode, "Choisir un salon…")))

    def guild(self) -> discord.Guild | None:
        return self.bot.get_guild(self.guild_id)

    async def render(self) -> discord.Embed:
        guild = self.guild()
        if guild is None:
            return discord.Embed(
                title="Serveur indisponible",
                description="Le bot n'est plus présent sur ce serveur.",
                color=discord.Color.red(),
            )
        config = await self.bot.config_store.get_guild(guild.id)
        state = (
            "Désactivé"
            if config.get("commands_disabled")
            else "Maintenance"
            if config.get("maintenance_mode")
            else "Actif"
        )
        embed = discord.Embed(
            title=f"{self._section_title()} · {guild.name}",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        if self.section == "home":
            embed.description = (
                f"**Membres :** {guild.member_count if guild.member_count is not None else 'inconnu'}\n"
                f"**Propriétaire :** {str(guild.owner) if guild.owner else f'ID {guild.owner_id}'}\n"
                f"**État du bot :** {state}\n"
                f"**ID :** `{guild.id}`\n\n"
                f"**Permissions du bot**\n{_permission_lines(guild)}"
            )
        elif self.section == "features":
            embed.description = "\n".join(
                f"{'🟢' if feature_is_enabled(config, key) else '⚪'} **{label}** — "
                f"{'activé' if feature_is_enabled(config, key) else 'désactivé'}"
                for key, label in FEATURE_LABELS.items()
            )
            embed.set_footer(text="Choisissez une fonctionnalité dans le menu pour la basculer.")
        elif self.section == "commands":
            disabled = config.get("disabled_commands", [])
            disabled = disabled if isinstance(disabled, list) else []
            enabled_count = sum(
                command.name != "owner" and not command.name.startswith("owner-")
                for command in self.bot.tree.get_commands()
            ) - len(disabled)
            embed.description = (
                f"Commandes activées : **{max(0, enabled_count)}**\n"
                f"Commandes désactivées : **{len(disabled)}**\n\n"
                "Choisissez une commande dans le menu pour changer son état. "
                "Les commandes OWNER ne sont pas modifiables ici."
            )
            embed.set_footer(text="Les commandes désactivées restent visibles dans Discord mais sont refusées par le bot.")
        elif self.section == "moderation":
            target = await self._resolve_member(guild, self.target_member_id) if self.target_member_id else None
            if target is None:
                embed.description = (
                    "Sélectionnez un membre dans le menu. Les actions disponibles dépendront "
                    "des permissions et de la hiérarchie du bot sur ce serveur."
                )
            else:
                embed.description = (
                    f"Membre sélectionné : {target.mention} (`{target.id}`)\n"
                    f"Rôle le plus élevé : **{target.top_role.name}**\n\n"
                    "Les sanctions ne peuvent viser le propriétaire du serveur, le bot lui-même "
                    "ou un membre dont le rôle est égal ou supérieur au rôle du bot."
                )
                warnings = await self.bot.warning_store.get_warnings(guild.id, target.id)
                if warnings:
                    recent = list(reversed(warnings[-5:]))
                    lines = [
                        f"• {str(item.get('reason', 'Sans motif'))[:160]} "
                        f"({str(item.get('created_at', 'date inconnue'))[:10]})"
                        for item in recent
                    ]
                    embed.add_field(
                        name=f"Avertissements enregistrés : {len(warnings)}",
                        value="\n".join(lines),
                        inline=False,
                    )
                else:
                    embed.add_field(name="Avertissements enregistrés", value="Aucun", inline=False)
        elif self.section == "tickets":
            tickets = self._open_tickets(guild)
            staff_role = guild.get_role(int(config["staff_role_id"])) if config.get("staff_role_id") else None
            category = guild.get_channel(int(config["ticket_category_id"])) if config.get("ticket_category_id") else None
            embed.description = (
                f"**État :** {'activés' if feature_is_enabled(config, 'tickets') else 'désactivés'}\n"
                f"**Rôle staff :** {staff_role.mention if staff_role else 'non configuré'}\n"
                f"**Catégorie :** {category.mention if isinstance(category, discord.CategoryChannel) else 'non configurée'}\n"
                f"**Tickets ouverts visibles par le bot :** {len(tickets)}"
            )
            if self.selected_ticket_id:
                channel = guild.get_channel(self.selected_ticket_id)
                embed.add_field(
                    name="Ticket sélectionné",
                    value=channel.mention if isinstance(channel, discord.TextChannel) else "Introuvable",
                )
        elif self.section == "messages":
            channel = guild.get_channel(int(config["owner_message_channel_id"])) if config.get("owner_message_channel_id") else None
            embed.description = (
                f"Salon sélectionné : {channel.mention if isinstance(channel, discord.TextChannel) else 'aucun'}\n\n"
                "Choisissez le salon depuis le menu, puis envoyez un message, un embed ou une annonce."
            )
        elif self.section == "welcome":
            channel = guild.get_channel(int(config["welcome_channel_id"])) if config.get("welcome_channel_id") else None
            template = str(config.get("welcome_message") or "Bienvenue {member} sur {server} !")
            embed.description = (
                f"**Salon :** {channel.mention if isinstance(channel, discord.TextChannel) else 'non configuré'}\n"
                "**Accueil automatique :** désactivé selon votre choix\n\n"
                f"**Message configuré :**\n{template[:900]}"
            )
            embed.set_footer(text="Vous pouvez modifier et prévisualiser le texte. L'envoi automatique reste désactivé.")
        elif self.section == "verification":
            role = guild.get_role(int(config["verification_role_id"])) if config.get("verification_role_id") else None
            channel = guild.get_channel(int(config["verification_channel_id"])) if config.get("verification_channel_id") else None
            embed.description = (
                f"**État :** {'activée' if feature_is_enabled(config, 'verification') else 'désactivée'}\n"
                f"**Rôle :** {role.mention if role else 'non configuré'}\n"
                f"**Salon :** {channel.mention if isinstance(channel, discord.TextChannel) else 'non configuré'}"
            )
        elif self.section == "logs":
            channel = guild.get_channel(int(config["log_channel_id"])) if config.get("log_channel_id") else None
            categories = config.get("log_categories", {})
            categories = categories if isinstance(categories, dict) else {}
            lines = [
                f"{'🟢' if categories.get(key, True) else '⚪'} {label}"
                for key, label in LOG_CATEGORIES.items()
            ]
            embed.description = (
                f"**Salon :** {channel.mention if isinstance(channel, discord.TextChannel) else 'non configuré'}\n\n"
                + "\n".join(lines)
            )
        elif self.section == "stats":
            activity = await self.bot.activity_store.get_guild(guild.id)
            counters = activity.get("counters", {})
            embed.description = (
                f"**Commandes utilisées :** {counters.get('commands_total', 0)}\n"
                f"**Tickets créés :** {counters.get('tickets_created', 0)}\n"
                f"**Actions de modération :** {counters.get('moderation_actions', 0)}\n"
                f"**État :** {state}\n\n"
                "Les compteurs sont conservés localement et réinitialisés uniquement si les fichiers de données sont supprimés."
            )
        elif self.section == "control":
            embed.description = (
                f"**Commandes du bot :** {'désactivées' if config.get('commands_disabled') else 'activées'}\n"
                f"**Mode maintenance :** {'actif' if config.get('maintenance_mode') else 'inactif'}\n\n"
                "La réinitialisation supprime uniquement la configuration du bot pour ce serveur. "
                "Les avertissements, les tickets et les journaux statistiques restent conservés."
            )
        embed.set_footer(text="Centre OWNER privé · sélectionnez une action dans le menu inférieur")
        return embed

    def _section_title(self) -> str:
        return {
            "home": "Accueil",
            "features": "Fonctionnalités",
            "commands": "Commandes",
            "moderation": "Modération",
            "tickets": "Tickets",
            "messages": "Messages",
            "welcome": "Bienvenue",
            "verification": "Vérification",
            "logs": "Logs du bot",
            "stats": "Statistiques",
            "control": "Contrôle",
        }.get(self.section, "Centre OWNER")

    async def navigate(
        self,
        interaction: discord.Interaction,
        section: str,
        *,
        page: int = 0,
    ) -> None:
        if section == "picker":
            view = ServerPickerView(self.bot)
            await interaction.response.edit_message(embed=view.embed(), view=view)
            return
        if section == "close":
            await interaction.response.edit_message(
                content="Panneau OWNER fermé.",
                embed=None,
                view=None,
            )
            return
        view = OwnerDashboardView(self.bot, self.guild_id, section, page=page)
        await interaction.response.edit_message(embed=await view.render(), view=view)

    async def refresh(self, interaction: discord.Interaction) -> None:
        view = OwnerDashboardView(
            self.bot,
            self.guild_id,
            self.section,
            target_member_id=self.target_member_id,
            selected_ticket_id=self.selected_ticket_id,
            page=self.page,
        )
        await interaction.response.edit_message(embed=await view.render(), view=view)

    async def handle_action(self, interaction: discord.Interaction, action: str) -> None:
        guild = self.guild()
        if guild is None:
            await interaction.response.send_message("Le serveur n'est plus accessible au bot.", ephemeral=True)
            return
        if action.startswith("feature:"):
            await self._toggle_feature(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("moderation:"):
            await self._moderation_action(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("ticket:"):
            await self._ticket_action(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("message:"):
            await self._message_action(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("welcome:"):
            await self._welcome_action(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("verify:"):
            await self._verify_action(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("logs:"):
            await self._logs_action(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("stats:"):
            await self._stats_action(interaction, guild, action.split(":", 1)[1])
        elif action.startswith("control:"):
            await self._control_action(interaction, guild, action.split(":", 1)[1])

    async def _toggle_feature(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        feature: str,
    ) -> None:
        if feature not in FEATURE_LABELS:
            await interaction.response.send_message("Fonctionnalité inconnue.", ephemeral=True)
            return
        config = await self.bot.config_store.get_guild(guild.id)
        features = config.get("features", {})
        features = dict(features) if isinstance(features, dict) else {}
        current = feature_is_enabled(config, feature)
        features[feature] = not current
        await self.bot.config_store.set_guild_values(guild.id, features=features)
        await audit_owner_action(
            self.bot,
            guild,
            f"Fonctionnalité {FEATURE_LABELS[feature]} {'activée' if not current else 'désactivée'}",
            f"État précédent : {'activé' if current else 'désactivé'}.",
        )
        await self.refresh(interaction)

    async def toggle_command(self, interaction: discord.Interaction, command_name: str) -> None:
        guild = self.guild()
        command = self.bot.tree.get_command(command_name)
        if guild is None or command is None or command_name == "owner" or command_name.startswith("owner-"):
            await interaction.response.send_message("Cette commande ne peut pas être modifiée.", ephemeral=True)
            return
        config = await self.bot.config_store.get_guild(guild.id)
        disabled = config.get("disabled_commands", [])
        disabled = list(disabled) if isinstance(disabled, list) else []
        if command_name in disabled:
            disabled.remove(command_name)
            status = "réactivée"
        else:
            disabled.append(command_name)
            status = "désactivée"
        await self.bot.config_store.set_guild_values(
            guild.id,
            disabled_commands=sorted(set(disabled)),
        )
        await audit_owner_action(self.bot, guild, f"Commande /{command_name} {status}", "")
        await self.refresh(interaction)

    async def handle_channel(
        self,
        interaction: discord.Interaction,
        purpose: str,
        channel: discord.abc.GuildChannel,
    ) -> None:
        guild = self.guild()
        if guild is None or channel.guild.id != guild.id:
            await interaction.response.send_message(
                "Choisissez un salon de ce serveur.",
                ephemeral=True,
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message("Impossible de vérifier les permissions du bot.", ephemeral=True)
            return
        if purpose == "ticket_category":
            if not isinstance(channel, discord.CategoryChannel):
                await interaction.response.send_message("Choisissez une catégorie de salons.", ephemeral=True)
                return
            if not bot_member.guild_permissions.manage_channels or not channel.permissions_for(bot_member).view_channel:
                await interaction.response.send_message(
                    "Le bot doit pouvoir voir la catégorie et gérer les salons.",
                    ephemeral=True,
                )
                return
            await self.bot.config_store.set_guild_values(guild.id, ticket_category_id=channel.id)
            await audit_owner_action(self.bot, guild, "Catégorie des tickets modifiée", f"Catégorie : {channel.name}")
            await self.refresh(interaction)
            return
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Choisissez un salon textuel.", ephemeral=True)
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.view_channel:
            await interaction.response.send_message("Le bot ne peut pas voir ce salon.", ephemeral=True)
            return
        if purpose == "ticket_panel":
            if not permissions.send_messages or not permissions.embed_links:
                await interaction.response.send_message(
                    "Le bot doit pouvoir envoyer des messages et des embeds dans ce salon.",
                    ephemeral=True,
                )
                return
            await self._publish_ticket_panel(interaction, guild, channel)
            return
        if purpose == "verify_publish":
            await self._publish_verification_panel(interaction, guild, channel)
            return
        needs_embed = purpose in {"log_channel", "message_channel", "welcome_channel", "verify_channel"}
        if needs_embed and (not permissions.send_messages or not permissions.embed_links):
            await interaction.response.send_message(
                "Le bot doit pouvoir envoyer des messages et des embeds dans ce salon.",
                ephemeral=True,
            )
            return
        key_by_purpose = {
            "log_channel": "log_channel_id",
            "message_channel": "owner_message_channel_id",
            "welcome_channel": "welcome_channel_id",
            "verify_channel": "verification_channel_id",
        }
        config_key = key_by_purpose.get(purpose)
        if config_key is None:
            await interaction.response.send_message("Action inconnue.", ephemeral=True)
            return
        await self.bot.config_store.set_guild_values(guild.id, **{config_key: channel.id})
        await audit_owner_action(self.bot, guild, "Salon de bot modifié", f"{purpose} : #{channel.name}")
        await self.refresh(interaction)

    async def handle_role(
        self,
        interaction: discord.Interaction,
        purpose: str,
        role: discord.Role,
    ) -> None:
        guild = self.guild()
        bot_member = guild.me if guild else None
        if guild is None or role.guild.id != guild.id or bot_member is None:
            await interaction.response.send_message("Choisissez un rôle de ce serveur.", ephemeral=True)
            return
        if purpose == "ticket_staff":
            if role.is_default() or role.managed or role >= bot_member.top_role:
                await interaction.response.send_message(
                    "Le rôle staff doit être attribuable et inférieur au rôle le plus élevé du bot.",
                    ephemeral=True,
                )
                return
            await self.bot.config_store.set_guild_values(guild.id, staff_role_id=role.id)
            await audit_owner_action(self.bot, guild, "Rôle staff des tickets modifié", f"Rôle : {role.name}")
        elif purpose == "verification_role":
            error = verification_role_error(role, bot_member)
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return
            config = await self.bot.config_store.get_guild(guild.id)
            old_ids = config.get("verification_role_ids", [])
            old_ids = old_ids if isinstance(old_ids, list) else []
            role_ids = {int(value) for value in old_ids if str(value).isdigit()}
            role_ids.add(role.id)
            await self.bot.config_store.set_guild_values(
                guild.id,
                verification_role_id=role.id,
                verification_role_ids=sorted(role_ids),
            )
            self.bot.add_view(VerifyView(role.id))
            await audit_owner_action(self.bot, guild, "Rôle de vérification modifié", f"Rôle : {role.name}")
        await self.refresh(interaction)

    async def _publish_ticket_panel(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        channel: discord.TextChannel,
    ) -> None:
        config = await self.bot.config_store.get_guild(guild.id)
        staff_id = config.get("staff_role_id")
        staff_role = guild.get_role(int(staff_id)) if staff_id else None
        if staff_role is None:
            await interaction.response.send_message(
                "Choisissez d'abord le rôle staff dans la section Tickets.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Besoin d'aide ?",
            description=(
                "Ouvrez un ticket privé pour contacter l'équipe. "
                "Seul vous et le staff pourrez consulter votre demande."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Support · {guild.name}")
        view = TicketPanelView()
        try:
            message = await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Le bot n'a pas pu publier le panneau. Vérifiez ses permissions dans ce salon.",
                ephemeral=True,
            )
            return
        self.bot.add_view(view, message_id=message.id)
        await self.bot.config_store.set_guild_values(guild.id, ticket_panel_channel_id=channel.id)
        await self.bot.activity_store.record_event(
            guild.id,
            "tickets",
            "Panneau de tickets publié",
            actor_id=self.bot.owner_id,
            detail=f"Salon : {channel.name}",
        )
        await audit_owner_action(self.bot, guild, "Panneau de tickets publié", f"Salon : #{channel.name}")
        await interaction.response.send_message("Panneau de tickets publié.", ephemeral=True)

    async def _publish_verification_panel(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        channel: discord.TextChannel,
    ) -> None:
        config = await self.bot.config_store.get_guild(guild.id)
        role_id = config.get("verification_role_id")
        role = guild.get_role(int(role_id)) if role_id else None
        bot_member = guild.me
        if role is None or bot_member is None:
            await interaction.response.send_message(
                "Choisissez d'abord un rôle de vérification.",
                ephemeral=True,
            )
            return
        error = verification_role_error(role, bot_member)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.embed_links or not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "Le bot doit pouvoir envoyer des embeds et gérer les rôles pour publier la vérification.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Vérification du serveur",
            description=f"Cliquez sur **Se vérifier** pour obtenir le rôle {role.mention}.",
            color=discord.Color.green(),
        )
        view = VerifyView(role.id)
        try:
            message = await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Le bot n'a pas pu publier le panneau dans ce salon.",
                ephemeral=True,
            )
            return
        self.bot.add_view(view, message_id=message.id)
        await self.bot.config_store.set_guild_values(guild.id, verification_channel_id=channel.id)
        await audit_owner_action(self.bot, guild, "Panneau de vérification publié", f"Salon : #{channel.name}")
        await interaction.response.send_message("Panneau de vérification publié.", ephemeral=True)

    async def handle_action_ticket_list(self, interaction: discord.Interaction, guild: discord.Guild) -> None:
        view = OwnerDashboardView(self.bot, guild.id, "tickets", input_mode="ticket_list")
        await interaction.response.edit_message(embed=await view.render(), view=view)

    def _open_tickets(self, guild: discord.Guild) -> list[discord.TextChannel]:
        bot_member = guild.me
        if bot_member is None:
            return []
        tickets: list[discord.TextChannel] = []
        for channel in guild.text_channels:
            if not channel.permissions_for(bot_member).view_channel:
                continue
            if OWNER_RE.search(channel.topic or "") and (STATUS_RE.search(channel.topic or "") is None):
                continue
            owner_match = OWNER_RE.search(channel.topic or "")
            status_match = STATUS_RE.search(channel.topic or "")
            if owner_match and status_match and status_match.group(1) == "open":
                tickets.append(channel)
        return sorted(tickets, key=lambda item: item.name.casefold())

    async def _ticket_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        if action == "staff":
            view = OwnerDashboardView(self.bot, guild.id, "tickets", input_mode="ticket_staff")
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action == "category":
            view = OwnerDashboardView(self.bot, guild.id, "tickets", input_mode="ticket_category")
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action == "panel":
            view = OwnerDashboardView(self.bot, guild.id, "tickets", input_mode="ticket_panel")
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action == "list":
            await self.handle_action_ticket_list(interaction, guild)
        elif action == "close":
            await self._close_selected_ticket(interaction, guild)

    async def _close_selected_ticket(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
    ) -> None:
        channel = guild.get_channel(self.selected_ticket_id or 0)
        bot_member = guild.me
        if not isinstance(channel, discord.TextChannel) or bot_member is None:
            await interaction.response.send_message("Ticket introuvable.", ephemeral=True)
            return
        if not channel.permissions_for(bot_member).manage_channels:
            await interaction.response.send_message(
                "Le bot n'a pas la permission `Gérer les salons` sur ce ticket.",
                ephemeral=True,
            )
            return
        owner_match = OWNER_RE.search(channel.topic or "")
        if not owner_match:
            await interaction.response.send_message("Ce salon n'est pas un ticket reconnu.", ephemeral=True)
            return
        try:
            member = guild.get_member(int(owner_match.group(1)))
            if member is None:
                member = await guild.fetch_member(int(owner_match.group(1)))
            await channel.set_permissions(member, send_messages=False, add_reactions=False)
            closed_name = channel.name if channel.name.startswith("ferme-") else f"ferme-{channel.name}"[:100]
            await channel.edit(
                name=closed_name,
                topic=f"owner_id={member.id};status=closed",
                reason="Ticket fermé depuis le centre OWNER",
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord a refusé la fermeture du ticket. Vérifiez les permissions du bot.",
                ephemeral=True,
            )
            return
        await log_action(
            self.bot,
            guild,
            "Ticket fermé depuis le centre OWNER",
            f"Ticket : #{channel.name}\nAuteur : `{member.id}`",
            category="tickets",
            event_kind="ticket_closed",
            actor_id=self.bot.owner_id,
            target_id=member.id,
        )
        await audit_owner_action(self.bot, guild, "Ticket fermé", f"Salon : #{channel.name}")
        await interaction.response.send_message("Ticket fermé.", ephemeral=True)

    async def _message_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        if action == "channel":
            view = OwnerDashboardView(self.bot, guild.id, "messages", input_mode="message_channel")
            await interaction.response.edit_message(embed=await view.render(), view=view)
            return
        config = await self.bot.config_store.get_guild(guild.id)
        channel_id = config.get("owner_message_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Choisissez d'abord le salon de destination.",
                ephemeral=True,
            )
            return
        modal = OwnerMessageModal(self.bot, guild.id, channel.id, action)
        await interaction.response.send_modal(modal)

    async def _welcome_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        config = await self.bot.config_store.get_guild(guild.id)
        if action == "channel":
            view = OwnerDashboardView(self.bot, guild.id, "welcome", input_mode="welcome_channel")
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action == "message":
            modal = WelcomeMessageModal(
                self.bot,
                guild.id,
                str(config.get("welcome_message") or "Bienvenue {member} sur {server} !"),
            )
            await interaction.response.send_modal(modal)
        elif action == "preview":
            channel_id = config.get("welcome_channel_id")
            channel = guild.get_channel(int(channel_id)) if channel_id else None
            template = str(config.get("welcome_message") or "Bienvenue {member} sur {server} !")
            preview = template.replace("{member}", "Alex").replace("{server}", guild.name)[:2000]
            embed = discord.Embed(
                title="Aperçu du message de bienvenue",
                description=preview,
                color=discord.Color.blurple(),
            )
            embed.set_footer(
                text=f"Salon : #{channel.name}" if isinstance(channel, discord.TextChannel) else "Aucun salon choisi"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _verify_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        if action == "role":
            view = OwnerDashboardView(self.bot, guild.id, "verification", input_mode="verification_role")
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action == "channel":
            view = OwnerDashboardView(self.bot, guild.id, "verification", input_mode="verify_channel")
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action == "publish":
            config = await self.bot.config_store.get_guild(guild.id)
            channel_id = config.get("verification_channel_id")
            channel = guild.get_channel(int(channel_id)) if channel_id else None
            if not isinstance(channel, discord.TextChannel):
                view = OwnerDashboardView(self.bot, guild.id, "verification", input_mode="verify_publish")
                await interaction.response.edit_message(embed=await view.render(), view=view)
            else:
                await self._publish_verification_panel(interaction, guild, channel)

    async def _logs_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        if action == "channel":
            view = OwnerDashboardView(self.bot, guild.id, "logs", input_mode="log_channel")
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action == "categories":
            options = [
                discord.SelectOption(label=label, value=f"logs:toggle:{key}")
                for key, label in LOG_CATEGORIES.items()
            ]
            view = OwnerDashboardView(self.bot, guild.id, "logs")
            view.add_item(DashboardActionSelect(view, options, "Activer ou désactiver une catégorie…"))
            await interaction.response.edit_message(embed=await view.render(), view=view)
        elif action.startswith("toggle:"):
            category = action.split(":", 1)[1]
            if category not in LOG_CATEGORIES:
                await interaction.response.send_message("Catégorie de logs inconnue.", ephemeral=True)
                return
            config = await self.bot.config_store.get_guild(guild.id)
            categories = config.get("log_categories", {})
            categories = dict(categories) if isinstance(categories, dict) else {}
            categories[category] = categories.get(category, True) is False
            await self.bot.config_store.set_guild_values(guild.id, log_categories=categories)
            await audit_owner_action(
                self.bot,
                guild,
                f"Catégorie de logs {LOG_CATEGORIES[category]} {'activée' if categories[category] else 'désactivée'}",
                "",
            )
            await self.refresh(interaction)
        elif action == "recent":
            await self._show_recent(interaction, guild, "logs")

    async def _stats_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        if action == "recent":
            await self._show_recent(interaction, guild, "stats")

    async def _show_recent(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        return_section: str,
    ) -> None:
        activity = await self.bot.activity_store.get_guild(guild.id)
        events = list(reversed(activity.get("events", [])[-10:]))
        embed = discord.Embed(
            title=f"Dernières actions · {guild.name}",
            color=discord.Color.blurple(),
        )
        if not events:
            embed.description = "Aucune action enregistrée pour le moment."
        else:
            lines = []
            for event in events:
                try:
                    when = discord.utils.format_dt(
                        datetime.fromisoformat(str(event.get("created_at", ""))),
                        style="R",
                    )
                except ValueError:
                    when = "date inconnue"
                actor_id = event.get("actor_id")
                actor = f" · <@{actor_id}>" if actor_id else ""
                lines.append(
                    f"• **{str(event.get('action', 'Action'))[:100]}**{actor} · {when}"
                )
            embed.description = "\n".join(lines)[:4000]
        embed.set_footer(text="Historique local limité aux 500 événements les plus récents")
        view = OwnerDashboardView(self.bot, guild.id, return_section)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _control_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        config = await self.bot.config_store.get_guild(guild.id)
        if action == "commands":
            new_value = not bool(config.get("commands_disabled"))
            await self.bot.config_store.set_guild_values(guild.id, commands_disabled=new_value)
            await audit_owner_action(
                self.bot,
                guild,
                "Commandes du bot " + ("désactivées" if new_value else "réactivées"),
                "",
            )
            await self.refresh(interaction)
        elif action == "maintenance":
            new_value = not bool(config.get("maintenance_mode"))
            await self.bot.config_store.set_guild_values(guild.id, maintenance_mode=new_value)
            await audit_owner_action(
                self.bot,
                guild,
                "Mode maintenance " + ("activé" if new_value else "désactivé"),
                "",
            )
            await self.refresh(interaction)
        elif action == "reset":
            view = ResetConfigConfirmView(self.bot, guild.id)
            await interaction.response.send_message(
                f"Confirmez la réinitialisation de la configuration du bot pour **{guild.name}**. "
                "Les avertissements, tickets et statistiques ne seront pas supprimés.",
                view=view,
                ephemeral=True,
            )
        elif action == "leave":
            view = LeaveConfirmView(self.bot, guild.id, stage=1)
            await interaction.response.send_message(
                f"Voulez-vous vraiment faire quitter **{guild.name}** au bot ? "
                "Une seconde confirmation sera demandée.",
                view=view,
                ephemeral=True,
            )

    async def _moderation_action(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        action: str,
    ) -> None:
        if self.target_member_id is None:
            await interaction.response.send_message("Sélectionnez d'abord un membre.", ephemeral=True)
            return
        if action == "warnings":
            await self.refresh(interaction)
            return
        if action == "remove_warn":
            view = RemoveWarningConfirmView(self.bot, guild.id, self.target_member_id)
            await interaction.response.send_message(
                "Confirmez la suppression du dernier avertissement enregistré pour ce membre.",
                view=view,
                ephemeral=True,
            )
            return
        modal = ModerationActionModal(self.bot, guild.id, self.target_member_id, action)
        await interaction.response.send_modal(modal)

    async def _resolve_member(
        self,
        guild: discord.Guild,
        member_id: int | None,
    ) -> discord.Member | None:
        if member_id is None:
            return None
        member = guild.get_member(member_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(member_id)
        except discord.HTTPException:
            return None


async def _execute_moderation(
    bot: SlashCommandBot,
    guild: discord.Guild,
    member_id: int,
    action: str,
    reason: str,
    duration: str | None = None,
) -> str:
    member = guild.get_member(member_id)
    if member is None:
        member = await guild.fetch_member(member_id)
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Impossible de vérifier le rôle du bot.")
    if member.id in {guild.owner_id, bot.user.id if bot.user else 0}:
        raise ValueError("Le propriétaire du serveur ou le bot ne peut pas être ciblé.")
    if member.top_role >= bot_member.top_role:
        raise ValueError("Le rôle du membre est égal ou supérieur à celui du bot.")
    permissions = bot_member.guild_permissions
    now = discord.utils.utcnow()
    if action == "warn":
        if not permissions.moderate_members:
            raise PermissionError("Le bot doit posséder la permission Timeout pour enregistrer un avertissement.")
        count = await bot.warning_store.add_warning(guild.id, member.id, bot.owner_id, reason)
        title = "Avertissement enregistré"
        message = f"Avertissement enregistré pour {member.display_name} · total : {count}."
    elif action == "timeout":
        if not permissions.moderate_members:
            raise PermissionError("Le bot ne possède pas la permission Timeout.")
        parsed = parse_timeout_duration(duration or "")
        if parsed is None:
            raise ValueError("Durée invalide. Utilisez 15m, 2h, 3d ou 1w (maximum 28 jours).")
        await member.timeout(parsed, reason=f"Centre OWNER · {reason}")
        title = "Timeout appliqué"
        message = f"Timeout appliqué à {member.display_name} pour {duration}."
    elif action == "kick":
        if not permissions.kick_members:
            raise PermissionError("Le bot ne possède pas la permission Expulser.")
        await member.kick(reason=f"Centre OWNER · {reason}")
        title = "Membre expulsé"
        message = f"{member.display_name} a été expulsé."
    elif action == "ban":
        if not permissions.ban_members:
            raise PermissionError("Le bot ne possède pas la permission Bannir.")
        await member.ban(reason=f"Centre OWNER · {reason}", delete_message_seconds=0)
        title = "Membre banni"
        message = f"{member.display_name} a été banni."
    else:
        raise ValueError("Action de modération inconnue.")
    await log_action(
        bot,
        guild,
        title,
        f"Membre : {member} (`{member.id}`)\nAuteur : OWNER (`{bot.owner_id}`)\nRaison : {reason}",
        category="moderation",
        event_kind="moderation",
        actor_id=bot.owner_id,
        target_id=member.id,
    )
    await audit_owner_action(bot, guild, title, f"Membre : {member} (`{member.id}`)\nRaison : {reason}")
    return message


class OwnerMessageModal(discord.ui.Modal):
    def __init__(
        self,
        bot: SlashCommandBot,
        guild_id: int,
        channel_id: int,
        action: str,
    ) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.action = action
        if action == "send":
            super().__init__(title="Envoyer un message")
            self.content = discord.ui.TextInput(
                label="Message",
                style=discord.TextStyle.paragraph,
                max_length=2000,
            )
            self.add_item(self.content)
        else:
            super().__init__(title="Créer un embed" if action == "embed" else "Créer une annonce")
            self.title_input = discord.ui.TextInput(label="Titre", max_length=256)
            self.content = discord.ui.TextInput(
                label="Contenu",
                style=discord.TextStyle.paragraph,
                max_length=4000,
            )
            self.add_item(self.title_input)
            self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.bot):
            return
        guild = self.bot.get_guild(self.guild_id)
        channel = guild.get_channel(self.channel_id) if guild else None
        bot_member = guild.me if guild else None
        if not isinstance(channel, discord.TextChannel) or bot_member is None:
            await interaction.response.send_message("Le salon n'est plus accessible.", ephemeral=True)
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.view_channel or not permissions.send_messages:
            await interaction.response.send_message(
                "Le bot ne peut pas envoyer de messages dans ce salon.",
                ephemeral=True,
            )
            return
        if self.action != "send" and not permissions.embed_links:
            await interaction.response.send_message(
                "Le bot n'a pas la permission d'intégrer des liens dans ce salon.",
                ephemeral=True,
            )
            return
        message_content = str(self.content.value)
        try:
            if self.action == "send":
                await channel.send(message_content, allowed_mentions=discord.AllowedMentions.none())
                action_name = "Message OWNER envoyé"
            else:
                title = str(self.title_input.value)
                embed = discord.Embed(
                    title=title,
                    description=message_content,
                    color=discord.Color.blurple(),
                )
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                action_name = "Annonce OWNER envoyée" if self.action == "announce" else "Embed OWNER envoyé"
        except discord.HTTPException:
            await interaction.response.send_message("Discord n'a pas pu envoyer le contenu.", ephemeral=True)
            return
        await audit_owner_action(self.bot, guild, action_name, f"Salon : #{channel.name}")
        await interaction.response.send_message(f"Contenu envoyé dans #{channel.name}.", ephemeral=True)


class WelcomeMessageModal(discord.ui.Modal):
    def __init__(self, bot: SlashCommandBot, guild_id: int, current_value: str) -> None:
        super().__init__(title="Modifier le message de bienvenue")
        self.bot = bot
        self.guild_id = guild_id
        self.message_input = discord.ui.TextInput(
            label="Texte · variables {member} et {server}",
            style=discord.TextStyle.paragraph,
            max_length=1900,
            default=current_value[:1900],
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.bot):
            return
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message("Le serveur n'est plus accessible.", ephemeral=True)
            return
        value = str(self.message_input.value).strip()
        if not value:
            await interaction.response.send_message("Le message ne peut pas être vide.", ephemeral=True)
            return
        await self.bot.config_store.set_guild_values(guild.id, welcome_message=value)
        await audit_owner_action(self.bot, guild, "Message de bienvenue modifié", "")
        await interaction.response.send_message(
            "Message enregistré. L'accueil automatique reste désactivé selon votre choix.",
            ephemeral=True,
        )


class ModerationActionModal(discord.ui.Modal):
    def __init__(
        self,
        bot: SlashCommandBot,
        guild_id: int,
        member_id: int,
        action: str,
    ) -> None:
        titles = {
            "warn": "Avertir un membre",
            "timeout": "Mettre en timeout",
            "kick": "Expulser un membre",
            "ban": "Bannir un membre",
        }
        super().__init__(title=titles.get(action, "Action de modération"))
        self.bot = bot
        self.guild_id = guild_id
        self.member_id = member_id
        self.action = action
        self.reason = discord.ui.TextInput(
            label="Raison",
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.add_item(self.reason)
        if action == "timeout":
            self.duration = discord.ui.TextInput(
                label="Durée (ex. 15m, 2h, 3d, 1w)",
                max_length=8,
            )
            self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.bot):
            return
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message("Le serveur n'est plus accessible.", ephemeral=True)
            return
        reason = str(self.reason.value).strip()
        if not reason:
            await interaction.response.send_message("La raison est obligatoire.", ephemeral=True)
            return
        duration = str(getattr(self, "duration", None).value) if hasattr(self, "duration") else None
        if self.action in {"kick", "ban"}:
            view = ModerationConfirmView(
                self.bot,
                guild.id,
                self.member_id,
                self.action,
                reason,
            )
            await interaction.response.send_message(
                f"Confirmez l'action **{self.action}** sur le membre sélectionné.",
                view=view,
                ephemeral=True,
            )
            return
        try:
            message = await _execute_moderation(
                self.bot,
                guild,
                self.member_id,
                self.action,
                reason,
                duration,
            )
        except (ValueError, PermissionError, discord.HTTPException, RuntimeError) as exc:
            await interaction.response.send_message(f"Action refusée : {str(exc)[:300]}", ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)


class ModerationConfirmView(OwnerOnlyView):
    def __init__(
        self,
        bot: SlashCommandBot,
        guild_id: int,
        member_id: int,
        action: str,
        reason: str,
    ) -> None:
        super().__init__(bot, timeout=180)
        self.guild_id = guild_id
        self.member_id = member_id
        self.action = action
        self.reason = reason

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger, row=0)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_owner(interaction, self.bot):
            return
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message("Le serveur n'est plus accessible.", ephemeral=True)
            return
        try:
            message = await _execute_moderation(
                self.bot,
                guild,
                self.member_id,
                self.action,
                self.reason,
            )
        except (ValueError, PermissionError, discord.HTTPException, RuntimeError) as exc:
            await interaction.response.send_message(f"Action refusée : {str(exc)[:300]}", ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_owner(interaction, self.bot):
            return
        await interaction.response.edit_message(content="Action annulée.", view=None)


class RemoveWarningConfirmView(OwnerOnlyView):
    def __init__(self, bot: SlashCommandBot, guild_id: int, member_id: int) -> None:
        super().__init__(bot, timeout=180)
        self.guild_id = guild_id
        self.member_id = member_id

    @discord.ui.button(label="Supprimer le dernier warn", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_owner(interaction, self.bot):
            return
        removed = await self.bot.warning_store.remove_last_warning(self.guild_id, self.member_id)
        if removed is None:
            await interaction.response.send_message("Aucun avertissement à supprimer.", ephemeral=True)
            return
        guild = self.bot.get_guild(self.guild_id)
        if guild:
            await audit_owner_action(self.bot, guild, "Avertissement supprimé", f"Membre : `{self.member_id}`")
        await interaction.response.send_message("Dernier avertissement supprimé.", ephemeral=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_owner(interaction, self.bot):
            return
        await interaction.response.edit_message(content="Suppression annulée.", view=None)


class ResetConfigConfirmView(OwnerOnlyView):
    def __init__(self, bot: SlashCommandBot, guild_id: int) -> None:
        super().__init__(bot, timeout=180)
        self.guild_id = guild_id

    @discord.ui.button(label="Réinitialiser la configuration", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_owner(interaction, self.bot):
            return
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message("Le serveur n'est plus accessible.", ephemeral=True)
            return
        await self.bot.config_store.remove_guild_values(self.guild_id, *list(await self._config_keys()))
        await audit_owner_action(self.bot, guild, "Configuration du bot réinitialisée", "")
        await interaction.response.send_message(
            "Configuration réinitialisée. Les avertissements, tickets et statistiques sont conservés.",
            ephemeral=True,
        )

    async def _config_keys(self) -> set[str]:
        config = await self.bot.config_store.get_guild(self.guild_id)
        return set(config)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_owner(interaction, self.bot):
            return
        await interaction.response.edit_message(content="Réinitialisation annulée.", view=None)


class LeaveConfirmView(OwnerOnlyView):
    def __init__(self, bot: SlashCommandBot, guild_id: int, stage: int) -> None:
        super().__init__(bot, timeout=180)
        self.guild_id = guild_id
        self.stage = stage
        if stage == 1:
            self.add_item(LeaveStepButton(self, final=False))
            self.add_item(LeaveStepButton(self, final=True, cancel=True))
        else:
            self.add_item(LeaveStepButton(self, final=True))
            self.add_item(LeaveStepButton(self, final=True, cancel=True))


class LeaveStepButton(discord.ui.Button):
    def __init__(
        self,
        panel: LeaveConfirmView,
        *,
        final: bool,
        cancel: bool = False,
    ) -> None:
        self.panel = panel
        self.final = final
        self.cancel_action = cancel
        label = "Annuler" if cancel else "Confirmer le départ" if not final else "Quitter définitivement"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary if cancel else discord.ButtonStyle.danger,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await require_owner(interaction, self.panel.bot):
            return
        if self.cancel_action:
            await interaction.response.edit_message(content="Départ annulé.", view=None)
            return
        if not self.final:
            view = LeaveConfirmView(self.panel.bot, self.panel.guild_id, stage=2)
            await interaction.response.edit_message(
                content="Dernière confirmation : le bot quittera ce serveur et ne pourra revenir qu'après une nouvelle invitation.",
                view=view,
            )
            return
        guild = self.panel.bot.get_guild(self.panel.guild_id)
        if guild is None:
            await interaction.response.send_message("Le bot n'est plus présent sur ce serveur.", ephemeral=True)
            return
        guild_name = guild.name
        await interaction.response.defer(ephemeral=True, thinking=True)
        await guild.leave()
        await interaction.followup.send(f"Le bot a quitté **{guild_name}**.", ephemeral=True)
