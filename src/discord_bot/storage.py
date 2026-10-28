"""Small atomic JSON stores for per-server settings and moderation warnings."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class JsonStore:
    def __init__(self, filename: str) -> None:
        self.path = DATA_DIR / filename
        self.data: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        async with self._lock:
            if not self.path.exists():
                self.data = {}
                return
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Impossible de lire le fichier de données {self.path.name}.") from exc
            if not isinstance(loaded, dict):
                raise RuntimeError(f"Le fichier de données {self.path.name} doit contenir un objet JSON.")
            self.data = loaded

    async def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        serialized = json.dumps(self.data, ensure_ascii=False, indent=2)
        await asyncio.to_thread(temp_path.write_text, serialized, encoding="utf-8")
        await asyncio.to_thread(os.replace, temp_path, self.path)


class GuildConfigStore(JsonStore):
    def __init__(self) -> None:
        super().__init__("guild_settings.json")

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        async with self._lock:
            return dict(self.data.get(str(guild_id), {}))

    async def set_guild_values(self, guild_id: int, **values: Any) -> dict[str, Any]:
        async with self._lock:
            key = str(guild_id)
            current = dict(self.data.get(key, {}))
            current.update(values)
            self.data[key] = current
            await self._save()
            return dict(current)

    async def remove_guild_values(self, guild_id: int, *keys: str) -> dict[str, Any]:
        async with self._lock:
            key = str(guild_id)
            current = dict(self.data.get(key, {}))
            for name in keys:
                current.pop(name, None)
            if current:
                self.data[key] = current
            else:
                self.data.pop(key, None)
            await self._save()
            return dict(current)

    async def all_guilds(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [dict(value) for value in self.data.values() if isinstance(value, dict)]


class WarningStore(JsonStore):
    def __init__(self) -> None:
        super().__init__("warnings.json")

    async def add_warning(
        self,
        guild_id: int,
        member_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        async with self._lock:
            guild_warnings = self.data.setdefault(str(guild_id), {})
            if not isinstance(guild_warnings, dict):
                raise RuntimeError("Les données d'avertissements de ce serveur sont invalides.")
            warnings = guild_warnings.setdefault(str(member_id), [])
            if not isinstance(warnings, list):
                raise RuntimeError("La liste des avertissements de ce membre est invalide.")
            warnings.append(
                {
                    "reason": reason,
                    "moderator_id": moderator_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            await self._save()
            return len(warnings)

    async def get_warnings(self, guild_id: int, member_id: int) -> list[dict[str, Any]]:
        async with self._lock:
            guild_warnings = self.data.get(str(guild_id), {})
            if not isinstance(guild_warnings, dict):
                raise RuntimeError("Les données d'avertissements de ce serveur sont invalides.")
            warnings = guild_warnings.get(str(member_id), [])
            if not isinstance(warnings, list):
                raise RuntimeError("La liste des avertissements de ce membre est invalide.")
            return [dict(item) for item in warnings if isinstance(item, dict)]

    async def remove_last_warning(self, guild_id: int, member_id: int) -> dict[str, Any] | None:
        async with self._lock:
            guild_key = str(guild_id)
            member_key = str(member_id)
            guild_warnings = self.data.get(guild_key, {})
            if not isinstance(guild_warnings, dict):
                raise RuntimeError("Les données d'avertissements de ce serveur sont invalides.")
            warnings = guild_warnings.get(member_key, [])
            if not isinstance(warnings, list):
                raise RuntimeError("La liste des avertissements de ce membre est invalide.")
            if not warnings:
                return None
            removed = warnings.pop()
            if not warnings:
                guild_warnings.pop(member_key, None)
            if not guild_warnings:
                self.data.pop(guild_key, None)
            await self._save()
            return dict(removed) if isinstance(removed, dict) else {}


class ActivityStore(JsonStore):
    """Persist command usage and bot actions for per-server dashboards."""

    def __init__(self) -> None:
        super().__init__("bot_activity.json")

    async def record_event(
        self,
        guild_id: int,
        kind: str,
        action: str,
        *,
        actor_id: int | None = None,
        target_id: int | None = None,
        detail: str = "",
    ) -> None:
        async with self._lock:
            guild_key = str(guild_id)
            guild_data = self.data.setdefault(guild_key, {})
            if not isinstance(guild_data, dict):
                raise RuntimeError("Les données d'activité de ce serveur sont invalides.")
            events = guild_data.setdefault("events", [])
            if not isinstance(events, list):
                raise RuntimeError("Le journal d'activité de ce serveur est invalide.")
            event: dict[str, Any] = {
                "kind": kind[:40],
                "action": action[:100],
                "created_at": datetime.now(UTC).isoformat(),
                "detail": detail[:600],
            }
            if actor_id is not None:
                event["actor_id"] = actor_id
            if target_id is not None:
                event["target_id"] = target_id
            events.append(event)
            del events[:-500]

            counters = guild_data.setdefault("counters", {})
            if not isinstance(counters, dict):
                counters = {}
                guild_data["counters"] = counters
            if kind == "command":
                counters["commands_total"] = int(counters.get("commands_total", 0)) + 1
                command_counts = counters.setdefault("commands", {})
                if isinstance(command_counts, dict):
                    command_counts[action] = int(command_counts.get(action, 0)) + 1
            elif kind == "ticket":
                counters["tickets_created"] = int(counters.get("tickets_created", 0)) + 1
            elif kind == "moderation":
                counters["moderation_actions"] = int(counters.get("moderation_actions", 0)) + 1
            await self._save()

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        async with self._lock:
            data = self.data.get(str(guild_id), {})
            if not isinstance(data, dict):
                return {}
            return {
                "counters": dict(data.get("counters", {}))
                if isinstance(data.get("counters", {}), dict)
                else {},
                "events": [
                    dict(event)
                    for event in data.get("events", [])
                    if isinstance(event, dict)
                ]
                if isinstance(data.get("events", []), list)
                else [],
            }
