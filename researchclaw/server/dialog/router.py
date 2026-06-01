"""Dialog router — routes messages to appropriate handlers."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from researchclaw.pipeline.control_state import (
    read_control_state,
    recent_supervisor_events,
    summarize_control_state,
)
from researchclaw.server.dialog.intents import Intent, classify_intent
from researchclaw.server.dialog.session import ChatSession, SessionManager

logger = logging.getLogger(__name__)

_session_manager = SessionManager(
    os.environ.get(
        "RESEARCHCLAW_DIALOG_DIR",
        "/data2/lyc/researchclaw/dialog-sessions",
    )
)


async def route_message(raw_message: str, client_id: str) -> str:
    """Route incoming chat message and return response."""
    # Parse message (could be plain text or JSON)
    try:
        msg_data = json.loads(raw_message)
        text = msg_data.get("message", msg_data.get("text", raw_message))
    except (json.JSONDecodeError, TypeError):
        text = raw_message

    session = _session_manager.get_or_create(client_id)
    session.add_message("user", text)

    intent, confidence = classify_intent(text)
    logger.debug("Intent: %s (%.2f) for: %s", intent.value, confidence, text[:50])

    handler = _HANDLERS.get(intent, _handle_general)
    response = await handler(text, session)

    session.add_message("assistant", response)
    return response


async def _handle_help(text: str, session: ChatSession) -> str:
    return (
        "I can help you with:\n"
        "- **Select a research topic**: describe your area of interest\n"
        "- **Start a pipeline run**: say 'start experiment' or 'run pipeline'\n"
        "- **Check progress**: ask 'what stage are we at?'\n"
        "- **View results**: ask about metrics, accuracy, or results\n"
        "- **Modify settings**: change learning rate, epochs, etc.\n"
        "- **Edit paper**: suggest changes to abstract, introduction, etc.\n\n"
        "Just type naturally — I'll figure out what you need!"
    )


async def _handle_status(text: str, session: ChatSession) -> str:
    from researchclaw.dashboard.collector import DashboardCollector

    collector = DashboardCollector()
    runs = collector.collect_all()
    if not runs:
        return "No pipeline runs found. Start one with 'start pipeline'."

    active = [r for r in runs if r.is_active]
    if active:
        r = active[0]
        run_dir = Path(r.path)
        control_state = read_control_state(run_dir)
        observer_summary = summarize_control_state(run_dir, control_state) if control_state else {}
        lines = [
            f"**Active run**: {r.run_id}",
            f"- Stage: {r.current_stage}/23 ({r.current_stage_name})",
            f"- Status: {r.status}",
            f"- Topic: {r.topic or '(not set)'}",
        ]
        if control_state:
            lines.append(f"- Substep: {control_state.get('current_substep', '') or '(unknown)'}")
        if observer_summary.get("headline"):
            lines.append(f"- Focus: {observer_summary['headline']}")
        alerts = observer_summary.get("alerts")
        if isinstance(alerts, list) and alerts:
            lines.append(f"- Alerts: {', '.join(str(item) for item in alerts[:4])}")
        recent_events = recent_supervisor_events(run_dir, limit=1)
        if recent_events:
            latest_event = recent_events[-1]
            summary = str(latest_event.get("summary") or "").strip()
            event_type = str(latest_event.get("event_type") or "supervisor_event")
            lines.append(f"- Supervisor: {event_type} — {summary or '(no summary)'}")
        return "\n".join(lines)

    latest = runs[0]
    latest_control = read_control_state(Path(latest.path))
    latest_summary = summarize_control_state(Path(latest.path), latest_control) if latest_control else {}
    lines = [
        f"**Latest run**: {latest.run_id}",
        f"- Stage: {latest.current_stage}/23",
        f"- Status: {latest.status}",
        f"- Stages completed: {len(latest.stages_completed)}",
    ]
    if latest_summary.get("headline"):
        lines.append(f"- Focus: {latest_summary['headline']}")
    alerts = latest_summary.get("alerts")
    if isinstance(alerts, list) and alerts:
        lines.append(f"- Alerts: {', '.join(str(item) for item in alerts[:4])}")
    recent_events = recent_supervisor_events(Path(latest.path), limit=1)
    if recent_events:
        latest_event = recent_events[-1]
        summary = str(latest_event.get("summary") or "").strip()
        event_type = str(latest_event.get("event_type") or "supervisor_event")
        lines.append(f"- Supervisor: {event_type} — {summary or '(no summary)'}")
    return "\n".join(lines)


async def _handle_start(text: str, session: ChatSession) -> str:
    return (
        "To start a pipeline run, use the dashboard or API:\n"
        "```\n"
        "POST /api/pipeline/start\n"
        '{"topic": "your research topic", "auto_approve": true}\n'
        "```\n"
        "Or run from CLI: `researchclaw run -c config.yaml`\n\n"
        "Would you like me to help you set up the configuration?"
    )


async def _handle_topic(text: str, session: ChatSession) -> str:
    return (
        "Let me help you find a research direction!\n\n"
        "Please tell me:\n"
        "1. Your research **domain** (e.g., CV, NLP, RL, AI4Science)\n"
        "2. Any **specific interests** (e.g., robustness, efficiency, fairness)\n"
        "3. Your **target venue** (e.g., NeurIPS, ICML, ICLR)\n\n"
        "I'll suggest novel, timely research angles based on recent trends."
    )


async def _handle_config(text: str, session: ChatSession) -> str:
    return (
        "You can modify the configuration through:\n"
        "1. Edit `config.yaml` directly\n"
        "2. Use the wizard: `researchclaw wizard`\n"
        "3. Pass overrides when starting: "
        '`POST /api/pipeline/start {"config_overrides": {...}}`\n\n'
        "What setting would you like to change?"
    )


async def _handle_results(text: str, session: ChatSession) -> str:
    from researchclaw.dashboard.collector import DashboardCollector

    collector = DashboardCollector()
    runs = collector.collect_all()
    if not runs:
        return "No runs found yet. Start a pipeline first."

    latest = runs[0]
    if not latest.metrics:
        return f"Run {latest.run_id} has no metrics yet (stage {latest.current_stage}/23)."

    lines = [f"**Results for {latest.run_id}**:\n"]
    for key, value in latest.metrics.items():
        if isinstance(value, (int, float)):
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) if len(lines) > 1 else f"Metrics: {latest.metrics}"


async def _handle_paper(text: str, session: ChatSession) -> str:
    return (
        "Paper editing is available after Stage 17 (Paper Draft).\n\n"
        "I can help with:\n"
        "- Review and suggest improvements to the abstract\n"
        "- Check the introduction structure\n"
        "- Verify experiment descriptions match actual results\n"
        "- Improve related work coverage\n\n"
        "Which section would you like to work on?"
    )


async def _handle_general(text: str, session: ChatSession) -> str:
    return (
        "I'm your ResearchClaw assistant. I can help with:\n"
        "- Selecting research topics\n"
        "- Running experiments\n"
        "- Monitoring progress\n"
        "- Analyzing results\n"
        "- Editing papers\n\n"
        "What would you like to do?"
    )


_HANDLERS = {
    Intent.HELP: _handle_help,
    Intent.CHECK_STATUS: _handle_status,
    Intent.START_PIPELINE: _handle_start,
    Intent.TOPIC_SELECTION: _handle_topic,
    Intent.MODIFY_CONFIG: _handle_config,
    Intent.DISCUSS_RESULTS: _handle_results,
    Intent.EDIT_PAPER: _handle_paper,
    Intent.GENERAL_CHAT: _handle_general,
}
