"""Universal Goal Entry — set Hermes goals from any platform.

This module provides a unified interface for setting goals from:
- Slack (via slash command)
- Terminal (via /goal)
- Email (subject: "GOAL: ...")
- Remember The Milk (task with hermes-goal tag)
- Direct API call

Usage:
    from hermes_cli.goals_universal import set_goal_universal
    
    result = set_goal_universal(
        goal_text="Fix all lint errors",
        source="email",  # or "slack", "terminal", "rtm", "api"
        user_id="ayb",
        metadata={"email_subject": "GOAL: Fix lint errors"}
    )
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from hermes_cli.goals import GoalManager, GoalState, load_goal

logger = logging.getLogger(__name__)


@dataclass
class GoalRequest:
    """Standardized request for setting a goal from any platform."""
    goal_text: str
    source: str  # "slack", "terminal", "email", "rtm", "api", "webhook"
    user_id: str
    session_id: str
    metadata: Dict[str, Any] = None
    max_turns: int = 20
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass  
class GoalResponse:
    """Standardized response from setting a goal."""
    success: bool
    goal: Optional[str]
    session_id: str
    message: str
    status: str
    max_turns: int
    error: Optional[str] = None
    platform_replies: Dict[str, str] = None  # Platform-specific responses
    
    def __post_init__(self):
        if self.platform_replies is None:
            self.platform_replies = {}


def normalize_goal_text(text: str) -> str:
    """Clean and normalize goal text from any source.
    
    Handles:
    - Email subject prefixes (RE:, FW:, GOAL:)
    - Slack formatting
    - Multiple spaces/newlines
    - Leading/trailing punctuation
    """
    if not text:
        return ""
    
    # Remove email prefixes
    text = re.sub(r"^(RE:|FW:|FWD:)\s*", "", text, flags=re.IGNORECASE)
    
    # Remove explicit goal markers
    text = re.sub(r"^GOAL:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^/goal\s+", "", text)
    
    # Clean whitespace
    text = " ".join(text.split())
    
    return text.strip()


def generate_session_id(
    source: str,
    user_id: str,
    channel_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> str:
    """Generate a consistent session ID for cross-platform persistence.
    
    This ensures that a goal set via email can be resumed/queried via Slack
    or terminal if the user ID matches.
    """
    # Normalize components
    uid = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id.lower())
    src = source.lower()
    
    if channel_id:
        cid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(channel_id).lower())
        if thread_id:
            tid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(thread_id).lower())
            return f"{src}-{uid}-{cid}-{tid}"
        return f"{src}-{uid}-{cid}"
    
    return f"{src}-{uid}"


def set_goal_universal(
    goal_text: str,
    source: str,
    user_id: str,
    channel_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
    max_turns: int = 20,
    metadata: Optional[Dict[str, Any]] = None,
) -> GoalResponse:
    """Set a Hermes goal from any platform.
    
    This is the main entry point that should be called by:
    - Slack gateway handler
    - Terminal CLI command
    - Email processor
    - RTM bridge
    - Web API endpoints
    
    Args:
        goal_text: The goal description (will be normalized)
        source: Platform source ("slack", "terminal", "email", "rtm", "api")
        user_id: Unique user identifier
        channel_id: Optional channel/context identifier
        thread_id: Optional thread/session identifier
        explicit_session_id: Optional override (if None, auto-generate)
        max_turns: Max auto-continuation turns
        metadata: Extra platform-specific data
    
    Returns:
        GoalResponse with status and platform-formatted replies
    """
    metadata = metadata or {}
    
    # Normalize the goal text
    clean_goal = normalize_goal_text(goal_text)
    
    if not clean_goal:
        return GoalResponse(
            success=False,
            goal=None,
            session_id="",
            message="Goal text is empty after normalization",
            status="error",
            error="empty_goal",
            max_turns=max_turns,
        )
    
    # Generate or use session ID
    session_id = explicit_session_id or generate_session_id(
        source=source,
        user_id=user_id,
        channel_id=channel_id,
        thread_id=thread_id,
    )
    
    try:
        # Create the goal
        mgr = GoalManager(session_id=session_id, default_max_turns=max_turns)
        state = mgr.set(clean_goal)
        
        # Build platform-specific responses
        platform_replies = build_platform_replies(state, source)
        
        return GoalResponse(
            success=True,
            goal=state.goal,
            session_id=session_id,
            message=f"Goal set ({state.max_turns}-turn budget): {state.goal}",
            status=state.status,
            max_turns=state.max_turns,
            platform_replies=platform_replies,
        )
        
    except Exception as exc:
        logger.error("Failed to set universal goal: %s", exc)
        return GoalResponse(
            success=False,
            goal=None,
            session_id=session_id,
            message=f"Failed to set goal: {exc}",
            status="error",
            error=str(exc),
            max_turns=max_turns,
        )


def build_platform_replies(state: GoalState, source: str) -> Dict[str, str]:
    """Generate platform-formatted responses for a goal.
    
    Each platform gets a suitable format:
    - Slack: Rich text with emoji
    - Terminal: ANSI colors
    - Email: Plain text with headers
    - RTM: Concise text
    - API: JSON-safe
    """
    replies = {}
    
    # Slack format (rich)
    replies["slack"] = (
        f"⊙ Goal set ({state.max_turns}-turn budget): {state.goal}\n\n"
        f"I'll keep working until the goal is done, you pause/clear it, or the budget is exhausted.\n"
        f"• `/goal status` - Check progress\n"
        f"• `/goal pause` - Pause auto-continue\n"
        f"• `/goal resume` - Resume (resets counter)\n"
        f"• `/goal clear` - Drop the goal"
    )
    
    # Terminal format (ANSI)
    replies["terminal"] = (
        f"  ⊙ Goal set ({state.max_turns}-turn budget): {state.goal}\n"
        f"  I'll keep working until the goal is done, you pause/clear it, or the budget is exhausted.\n"
        f"  Controls: /goal status · /goal pause · /goal resume · /goal clear"
    )
    
    # Email format
    replies["email"] = (
        f"HERMES GOAL SET\n"
        f"================\n"
        f"Goal: {state.goal}\n"
        f"Turn budget: {state.max_turns}\n"
        f"Status: {state.status}\n\n"
        f"I'll auto-continue after each turn until complete, paused, or budget exhausted.\n\n"
        f"Reply commands:\n"
        f"- GOAL:STATUS - Check progress\n"
        f"- GOAL:PAUSE - Pause auto-continue\n"
        f"- GOAL:RESUME - Resume and reset counter\n"
        f"- GOAL:CLEAR - Drop the goal"
    )
    
    # RTM format (concise)
    replies["rtm"] = (
        f"⊙ Goal set ({state.max_turns} turns): {state.goal[:80]}\n"
        f"Use /goal status/pause/resume/clear to control."
    )
    
    # API format (JSON)
    replies["api"] = state.to_json()
    
    return replies


def handle_goal_control_command(
    command: str,
    user_id: str,
    source: str,
    channel_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
) -> Optional[str]:
    """Handle goal control commands from any platform.
    
    Commands:
    - "status" or "" - Show current state
    - "pause" - Pause the loop
    - "resume" - Resume and reset counter
    - "clear" - Drop the goal
    
    Returns response string or None if no goal exists.
    """
    session_id = explicit_session_id or generate_session_id(
        source=source,
        user_id=user_id,
        channel_id=channel_id,
        thread_id=thread_id,
    )
    
    try:
        mgr = GoalManager(session_id=session_id)
        
        if not mgr.has_goal():
            return "No active goal set." if source != "slack" else "No active goal set. Use `/goal <text>` to start one."
        
        cmd = command.strip().lower()
        
        if not cmd or cmd == "status":
            return mgr.status_line()
        
        if cmd == "pause":
            state = mgr.pause(reason="user-paused")
            return f"⏸ Goal paused: {state.goal}" if state else "No goal to pause."
        
        if cmd == "resume":
            state = mgr.resume()
            if state:
                return f"▶ Goal resumed: {state.goal}\nSend any message to continue."
            return "No goal to resume."
        
        if cmd in ("clear", "stop", "done"):
            had = mgr.has_goal()
            mgr.clear()
            return "✓ Goal cleared." if had else "No active goal."
        
        return f"Unknown goal command: {cmd}"
        
    except Exception as exc:
        logger.error("Failed to handle goal command: %s", exc)
        return f"Error: {exc}"


def list_user_goals(user_id: str) -> List[Dict[str, Any]]:
    """List all active goals for a user across all platforms.
    
    This is useful for cross-platform goal management — see all your
    active Hermes goals in one place.
    """
    # TODO: Implement session scanning in SessionDB
    # For now, return empty list (placeholder)
    return []


# Convenience exports for direct use
__all__ = [
    "set_goal_universal",
    "handle_goal_control_command",
    "normalize_goal_text",
    "generate_session_id",
    "list_user_goals",
    "GoalRequest",
    "GoalResponse",
]
