"""Server-side access checks for bot-owner commands and disabled servers."""

from __future__ import annotations

import discord
from discord import app_commands


class OwnerOnlyCheckFailure(app_commands.CheckFailure):
    """Raised when a user other than the configured owner calls an owner command."""


class GuildCommandsDisabledError(app_commands.CheckFailure):
    """Raised when a server's bot commands are disabled."""


def owner_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        owner_id = getattr(interaction.client, "owner_id", None)
        if owner_id is None or interaction.user.id != owner_id:
            raise OwnerOnlyCheckFailure
        return True

    return app_commands.check(predicate)
