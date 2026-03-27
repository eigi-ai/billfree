#!/usr/bin/env python3
"""
Extract the recent OpenClaw conversation transcript for summarization.

Reads the gateway-backed session store and transcript JSONL directly from disk.
This is intended to make "summarize the last 6 hours" deterministic inside the
BillFree skill instead of relying on model memory alone.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_AGENT_ID = "main"
DEFAULT_HOURS = 6


@dataclass
class SessionTarget:
    key: str
    session_id: str
    transcript_path: Path
    updated_at: datetime | None
    chat_type: str | None
    channel: str | None
    peer: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract recent OpenClaw conversation history from sessions.json + transcript JSONL."
    )
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("OPENCLAW_STATE_DIR", "~/.openclaw"),
        help="OpenClaw state directory (default: OPENCLAW_STATE_DIR or ~/.openclaw)",
    )
    parser.add_argument(
        "--agent-id",
        default=DEFAULT_AGENT_ID,
        help=f"Agent id (default: {DEFAULT_AGENT_ID})",
    )
    parser.add_argument(
        "--session-key",
        default=os.environ.get("OPENCLAW_SESSION_KEY") or os.environ.get("SESSION_KEY"),
        help="Exact OpenClaw session key to read (default: OPENCLAW_SESSION_KEY or SESSION_KEY when present)",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Filter session selection by channel, e.g. whatsapp",
    )
    parser.add_argument(
        "--peer",
        default=None,
        help="Filter session selection by peer/recipient id, e.g. +9185...",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_HOURS,
        help=f"Lookback window in hours (default: {DEFAULT_HOURS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text transcript",
    )
    parser.add_argument(
        "--allow-main",
        action="store_true",
        help="Allow selecting the shared main session (agent:<id>:main) when explicitly intended",
    )
    return parser.parse_args()


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    return None


def sessions_store_path(state_dir: Path, agent_id: str) -> Path:
    return state_dir / "agents" / agent_id / "sessions" / "sessions.json"


def load_sessions(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Session store not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in session store {path}: {exc}")


def build_target(
    key: str, entry: dict[str, Any], sessions_dir: Path
) -> SessionTarget | None:
    session_id = str(entry.get("sessionId", "")).strip()
    if not session_id:
        return None

    session_file = str(entry.get("sessionFile", "")).strip()
    if session_file:
        transcript_path = Path(session_file)
        if not transcript_path.exists():
            transcript_path = sessions_dir / f"{session_id}.jsonl"
    else:
        transcript_path = sessions_dir / f"{session_id}.jsonl"
    origin = entry.get("origin") or {}
    delivery = entry.get("deliveryContext") or {}
    peer = delivery.get("to") or entry.get("lastTo") or origin.get("to") or origin.get("from")

    return SessionTarget(
        key=key,
        session_id=session_id,
        transcript_path=transcript_path,
        updated_at=parse_dt(entry.get("updatedAt")),
        chat_type=entry.get("chatType") or origin.get("chatType"),
        channel=delivery.get("channel") or entry.get("lastChannel") or origin.get("channel") or origin.get("provider"),
        peer=str(peer) if peer is not None else None,
    )


def choose_target(
    sessions: dict[str, Any],
    sessions_dir: Path,
    session_key: str | None,
    channel: str | None,
    peer: str | None,
    allow_main: bool,
) -> SessionTarget:
    targets: list[SessionTarget] = []
    for key, entry in sessions.items():
        if not isinstance(entry, dict):
            continue
        target = build_target(key, entry, sessions_dir)
        if target is None:
            continue
        targets.append(target)

    if not targets:
        raise SystemExit("No sessions found in the session store.")

    if session_key:
        for target in targets:
            if target.key == session_key or target.session_id == session_key:
                if target.key.endswith(":main") and not allow_main:
                    raise SystemExit(
                        "Refusing to read the shared main session without --allow-main. "
                        "Pass the current non-main session key for direct/group isolation."
                    )
                return target
        raise SystemExit(f"Session not found for key/id: {session_key}")

    filtered = targets
    if channel:
        filtered = [t for t in filtered if (t.channel or "").lower() == channel.lower()]
    if peer:
        filtered = [t for t in filtered if t.peer == peer]

    if not session_key and not (channel and peer):
        raise SystemExit(
            "Refusing to guess a session from partial or missing scope. "
            "Pass --session-key for the current chat, or both --channel and --peer."
        )

    if not filtered:
        filters = ", ".join(
            part for part in [f"channel={channel}" if channel else "", f"peer={peer}" if peer else ""] if part
        )
        raise SystemExit(f"No matching sessions found ({filters}).")

    filtered.sort(key=lambda t: t.updated_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    if len(filtered) > 1:
        keys = ", ".join(target.key for target in filtered[:5])
        raise SystemExit(
            "Multiple sessions match the requested scope. Pass --session-key explicitly. "
            f"Matches: {keys}"
        )

    selected = filtered[0]
    if selected.key.endswith(":main") and not allow_main:
        raise SystemExit(
            "Refusing to read the shared main session without --allow-main. "
            "Use the exact current session key for isolated direct/group chats."
        )
    return selected


def extract_text_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


_METADATA_PREFIX_RE = re.compile(
    r"^Conversation info \(untrusted metadata\):.*?^Sender \(untrusted metadata\):.*?^```$\n?",
    re.DOTALL | re.MULTILINE,
)


def clean_message_text(role: str, text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    if role == "user":
        if cleaned.startswith("A new session was started via /new or /reset."):
            return ""
        if cleaned.startswith("System: [") and "HEARTBEAT.md" in cleaned:
            return ""
        if cleaned.startswith("Conversation info (untrusted metadata):"):
            parts = cleaned.split("\n\n", 2)
            if len(parts) == 3:
                cleaned = parts[2].strip()
        cleaned = _METADATA_PREFIX_RE.sub("", cleaned).strip()

    if role == "assistant":
        if cleaned.startswith("✅ New session started"):
            return ""
        if cleaned == "HEARTBEAT_OK":
            return ""

    return cleaned.strip()


def load_recent_messages(transcript_path: Path, cutoff: datetime) -> list[dict[str, Any]]:
    try:
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise SystemExit(f"Transcript not found: {transcript_path}")

    messages: list[dict[str, Any]] = []
    for raw_line in lines:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if entry.get("type") != "message":
            continue

        message = entry.get("message")
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue

        timestamp = parse_dt(entry.get("timestamp")) or parse_dt(message.get("timestamp"))
        if timestamp is None or timestamp < cutoff:
            continue

        text = clean_message_text(role, extract_text_blocks(message.get("content")))
        if not text:
            continue

        messages.append(
            {
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "role": role,
                "text": text,
            }
        )
    return messages


def emit_text(target: SessionTarget, cutoff: datetime, messages: list[dict[str, Any]]) -> None:
    print(f"Session key: {target.key}")
    print(f"Session id: {target.session_id}")
    print(f"Transcript: {target.transcript_path}")
    print(f"Window start (UTC): {cutoff.isoformat().replace('+00:00', 'Z')}")
    print("")
    print("---TRANSCRIPT START---")
    for item in messages:
        role = "User" if item["role"] == "user" else "Assistant"
        print(f"[{item['timestamp']}] {role}: {item['text']}")
    print("---TRANSCRIPT END---")


def main() -> int:
    args = parse_args()
    state_dir = Path(os.path.expanduser(args.state_dir)).resolve()
    store_path = sessions_store_path(state_dir, args.agent_id)
    sessions_dir = store_path.parent
    cutoff = datetime.now(tz=UTC) - timedelta(hours=args.hours)

    sessions = load_sessions(store_path)
    target = choose_target(
        sessions,
        sessions_dir,
        args.session_key,
        args.channel,
        args.peer,
        args.allow_main,
    )
    messages = load_recent_messages(target.transcript_path, cutoff)

    payload = {
        "sessionKey": target.key,
        "sessionId": target.session_id,
        "transcriptPath": str(target.transcript_path),
        "windowStartUtc": cutoff.isoformat().replace("+00:00", "Z"),
        "messageCount": len(messages),
        "messages": messages,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        emit_text(target, cutoff, messages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
