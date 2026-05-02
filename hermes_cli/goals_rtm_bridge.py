"""Remember The Milk (RTM) to Goal bridge — set Hermes goals from RTM tasks.

Watches RTM tasks with specific tags or prefixes and converts them to
Hermes goals. Can be run as a cron job.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# RTM tag that marks a task as a Hermes goal
GOAL_TAG = "hermes-goal"
GOAL_PREFIX = "GOAL:"


def parse_goal_from_rtm_task(task: Dict[str, Any]) -> Optional[str]:
    """Extract goal text from an RTM task.
    
    Match patterns:
    - Task has "hermes-goal" tag
    - Task name starts with "GOAL: " or "GOAL "
    - Task note contains "/goal <text>"
    
    Returns the goal text if found, None otherwise.
    """
    if not task:
        return None
    
    task_name = task.get("name", "")
    task_notes = task.get("notes", [])
    task_tags = task.get("tags", [])
    
    # Check for GOAL: prefix in task name
    if task_name.startswith(GOAL_PREFIX):
        return task_name[len(GOAL_PREFIX):].strip()
    
    if task_name.startswith("GOAL "):
        return task_name[5:].strip()
    
    # Check for hermes-goal tag
    if GOAL_TAG in task_tags:
        # Use the whole task name as the goal
        return task_name.strip()
    
    # Check notes for /goal command
    for note in task_notes:
        note_text = note.get("text", "") if isinstance(note, dict) else str(note)
        if note_text.strip().startswith("/goal "):
            return note_text.strip()[6:].strip()
    
    return None


def set_goal_from_rtm(
    goal_text: str,
    session_id: str,
    task_id: Optional[str] = None,
    max_turns: int = 20,
) -> Dict[str, Any]:
    """Set a goal from RTM task context.
    
    Creates a GoalManager and sets the goal, linking it back to the
    RTM task for tracking.
    """
    try:
        from hermes_cli.goals import GoalManager
        
        mgr = GoalManager(session_id=session_id, default_max_turns=max_turns)
        state = mgr.set(goal_text)
        
        return {
            "success": True,
            "goal": state.goal,
            "max_turns": state.max_turns,
            "status": state.status,
            "rtm_task_id": task_id,
            "message": f"⊙ Goal set ({state.max_turns}-turn budget): {state.goal}",
        }
    except Exception as exc:
        logger.error("Failed to set goal from RTM: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "rtm_task_id": task_id,
            "message": f"Failed to set goal: {exc}",
        }


def run_rtm_processor(
    list_name: Optional[str] = None,
    session_prefix: str = "rtm",
    complete_on_done: bool = True,
) -> List[Dict[str, Any]]:
    """Process RTM tasks and create Hermes goals.
    
    Scans RTM for tasks matching goal patterns and sets them up in
    Hermes. Can be run periodically via cron.
    
    Args:
        list_name: Specific RTM list to check (None = all lists)
        session_prefix: Prefix for generated session IDs
        complete_on_done: Whether to complete RTM task when goal is done
    
    Returns:
        List of processed goal results
    """
    results = []
    
    try:
        # Import RTM toolset (which has the API wrapper)
        from tools.rtm import get_tasks, complete_task
        
        # Get tasks - either from specific list or all
        if list_name:
            tasks = get_tasks(list_name=list_name, status="incomplete")
        else:
            tasks = get_tasks(status="incomplete")
        
        for task in tasks:
            try:
                goal_text = parse_goal_from_rtm_task(task)
                
                if not goal_text:
                    continue
                
                task_id = task.get("id")
                task_name = task.get("name", "")
                
                # Generate session ID from task
                session_id = f"{session_prefix}-{task_id}" if task_id else f"{session_prefix}-{hash(task_name)}"
                
                # Check if goal already active for this session
                try:
                    from hermes_cli.goals import GoalManager
                    mgr = GoalManager(session_id=session_id)
                    if mgr.has_goal():
                        logger.debug("Goal already active for %s", session_id)
                        continue
                except Exception:
                    pass
                
                # Set the goal
                result = set_goal_from_rtm(goal_text, session_id, task_id)
                
                if result["success"]:
                    results.append({
                        "rtm_task_id": task_id,
                        "rtm_task_name": task_name[:80],
                        "goal": goal_text,
                        "session_id": session_id,
                        "status": "set",
                    })
                
            except Exception as exc:
                logger.error("Failed to process RTM task %s: %s", task.get("id"), exc)
                continue
                
    except ImportError:
        logger.warning("RTM tools not available - skipping RTM goal processing")
    except Exception as exc:
        logger.error("RTM processor error: %s", exc)
    
    return results


def create_goal_task_in_rtm(
    goal_text: str,
    list_name: str = "Hermes",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an RTM task from a Hermes goal.
    
    This is useful for bidirectional sync — when setting a goal in
    Slack/CLI, create a linked RTM task for tracking.
    """
    try:
        from tools.rtm import add_task
        
        task_name = f"GOAL: {goal_text}"
        task_notes = notes or "Created from Hermes /goal command\nTag: hermes-goal"
        
        result = add_task(
            name=task_name,
            list_name=list_name,
            notes=task_notes,
            tags=[GOAL_TAG],
        )
        
        return {
            "success": True,
            "rtm_task_id": result.get("id"),
            "rtm_task_name": task_name,
            "list": list_name,
        }
        
    except ImportError:
        return {"success": False, "error": "RTM tools not available"}
    except Exception as exc:
        logger.error("Failed to create RTM task: %s", exc)
        return {"success": False, "error": str(exc)}


def get_active_goals_for_rtm_sync() -> List[Dict[str, Any]]:
    """Get all active Hermes goals that should be synced to RTM.
    
    Useful for keeping RTM tasks updated with goal status.
    """
    active_goals = []
    
    try:
        # This would need to query the SessionDB for active goals
        # For now, return empty list (placeholder)
        logger.debug("RTM sync not yet implemented")
        
    except Exception as exc:
        logger.error("Failed to get goals for RTM sync: %s", exc)
    
    return active_goals


def main():
    """CLI entry point for RTM goal processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process RTM tasks and set Hermes goals")
    parser.add_argument("--list", dest="list_name", help="Specific RTM list to check")
    parser.add_argument("--session-prefix", default="rtm", help="Prefix for session IDs")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't set goals")
    parser.add_argument("--create-task", help="Create an RTM task from a goal (bidirectional)")
    parser.add_argument("--to-list", default="Hermes", help="List for created tasks")
    
    args = parser.parse_args()
    
    if args.create_task:
        # Create RTM task from goal
        result = create_goal_task_in_rtm(args.create_task, args.to_list)
        if result["success"]:
            print(f"✓ Created RTM task: {result['rtm_task_name']}")
        else:
            print(f"✗ Failed: {result.get('error', 'unknown error')}")
        return 0 if result["success"] else 1
    
    # Process RTM -> Goals
    if args.dry_run:
        print("Dry run mode - parsing RTM tasks only")
    
    results = run_rtm_processor(
        list_name=args.list_name,
        session_prefix=args.session_prefix,
    )
    
    if results:
        print(f"\nProcessed {len(results)} RTM goals:")
        for r in results:
            print(f"  ✓ {r['rtm_task_name'][:60]}...")
            print(f"    Goal: {r['goal'][:80]}...")
            print(f"    Session: {r['session_id']}")
    else:
        print("\nNo RTM goal tasks found to process")
    
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
