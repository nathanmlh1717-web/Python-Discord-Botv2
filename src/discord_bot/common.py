"""Shared helpers for permission checks, moderation logs, and command replies."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot

LOGGER = logging.getLogger("discord_bot")
MENTIONS_NONE = discord.AllowedMentions.none()


def target_hierarchy_error(
    interaction: discord.Interaction,
    target: discord.Member,
) -> str | None:
    """Return a French explanation if the caller or bot cannot manage a target."""
    guild = interaction.guild
    actor = interaction.user
    if guild is None or not isinstance(actor, discord.Member):
        return "Cette commande doit être utilisée sur un serveur."
    if target.id == actor.id:
        return "Vous ne pouvez pas utiliser cette commande sur vous-même."
    if target.id == guild.owner_id:
        return "Le propriétaire du serveur ne peut pas être ciblé."
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return "Le rôle le plus élevé de ce membre est égal ou supérieur au vôtre."
    bot_member = guild.me
    if bot_member is None or target.top_role >= bot_member.top_role:
        return "Le rôle le plus élevé de ce membre est égal ou supérieur à celui du bot."
    return None


async def log_action(
    bot: SlashCommandBot,
    guild: discord.Guild,
    title: str,
    description: str,
    *,
    color: discord.Color = discord.Color.orange(),
) -> bool:
    """Send a moderation or ticket event to the configured log channel."""
    config = await bot.config_store.get_guild(guild.id)
    channel_id = config.get("log_channel_id")
    if not channel_id:
        LOGGER.info("Aucun salon de logs configuré pour le serveur %s.", guild.id)
        return False
    channel = guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        LOGGER.warning("Le salon de logs configuré est introuvable pour le serveur %s.", guild.id)
        return False
    embed = discord.Embed(title=title, description=description, color=color)
    try:
        await channel.send(embed=embed, allowed_mentions=MENTIONS_NONE)
    except discord.HTTPException:
        LOGGER.exception("Impossible d'envoyer un événement dans le salon de logs %s.", channel.id)
        return False
    return True


def parse_timeout_duration(value: str) -> timedelta | None:
    """Parse a duration like 15m, 2h, or 3d; Discord caps timeouts at 28 days."""
    if len(value) > 8:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*([mhdw])\s*", value, re.IGNORECASE)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    seconds = amount * multiplier
    if seconds < 60 or seconds > 28 * 86400:
        return None
    return timedelta(seconds=seconds)


def command_reason(reason: str, moderator: discord.abc.User) -> str:
    safe_reason = reason.strip()[:400] or "Aucune raison fournie."
    return f"{safe_reason} — par {moderator} ({moderator.id})"


def normalize_reason(reason: str) -> str | None:
    cleaned = reason.strip()
    if not cleaned or len(cleaned) > 500:
        return None
    return cleaned


def format_member(member: discord.Member) -> str:
    return f"{member.mention} (`{member.id}`)"
