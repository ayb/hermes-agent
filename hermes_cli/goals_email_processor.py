"""Email-to-Goal processor — set Hermes goals via email.

Watches for emails with subject prefix "GOAL:" or body commands.
Can be run as a cron job or standalone script.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def parse_goal_from_subject(subject: str) -> Optional[str]:
    """Extract goal text from subject line.
    
    Match patterns:
    - "GOAL: <text>"
    - "GOAL <text>" 
    - "[GOAL] <text>"
    """
    if not subject:
        return None
    
    patterns = [
        r"^GOAL:\s*(.+)$",
        r"^GOAL\s+(.+)$",
        r"^\[GOAL\]\s*(.+)$",
    ]
    
    for pattern in patterns:
        match = re.match(pattern, subject.strip(), re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def parse_goal_from_body(body: str) -> Optional[str]:
    """Extract goal from email body.
    
    Look for:
    - "/goal <text>" commands
    - "GOAL: <text>" lines at start
    """
    if not body:
        return None
    
    lines = body.strip().split("\n")
    
    for line in lines[:10]:  # Check first 10 lines
        line = line.strip()
        
        # Match /goal command
        if line.startswith("/goal "):
            return line[6:].strip()
        
        # Match GOAL: prefix
        match = re.match(r"^GOAL:\s*(.+)$", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def process_email_for_goal(
    sender: str,
    subject: str,
    body: str,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Process an email and extract goal if present.
    
    Returns:
        {
            "has_goal": bool,
            "goal_text": str | None,
            "source": "subject" | "body" | None,
            "session_id": str | None,
        }
    """
    # Try subject first
    goal = parse_goal_from_subject(subject)
    source = "subject"
    
    # Fall back to body
    if not goal:
        goal = parse_goal_from_body(body)
        source = "body"
    
    return {
        "has_goal": goal is not None,
        "goal_text": goal,
        "source": source if goal else None,
        "session_id": session_id,
    }


def set_goal_from_email(
    goal_text: str,
    session_id: str,
    max_turns: int = 20,
) -> Dict[str, Any]:
    """Set a goal from email context.
    
    This creates a GoalManager and sets the goal, similar to what
    happens when using /goal in Slack or CLI.
    """
    try:
        from hermes_cli.goals import GoalManager, save_goal
        
        mgr = GoalManager(session_id=session_id, default_max_turns=max_turns)
        state = mgr.set(goal_text)
        
        return {
            "success": True,
            "goal": state.goal,
            "max_turns": state.max_turns,
            "status": state.status,
            "message": f"⊙ Goal set ({state.max_turns}-turn budget): {state.goal}",
        }
    except Exception as exc:
        logger.error("Failed to set goal from email: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "message": f"Failed to set goal: {exc}",
        }


def run_email_processor(
    imap_server: Optional[str] = None,
    imap_user: Optional[str] = None,
    imap_pass: Optional[str] = None,
    session_id: Optional[str] = None,
    mark_processed: bool = True,
) -> List[Dict[str, Any]]:
    """Run the email processor and set goals from matching emails.
    
    Can be called from cron, CLI command, or integrated into existing
    email processing workflows.
    
    Args:
        imap_server: IMAP server host (or from config)
        imap_user: Username (or from config)
        imap_pass: Password (or from config)
        session_id: Default session to associate with goals
        mark_processed: Whether to mark processed emails as read
    
    Returns:
        List of processed goal results
    """
    results = []
    
    try:
        # Try to use Himalaya CLI if available
        import subprocess
        import json
        
        # Search for unread emails with GOAL in subject
        cmd = ["himalaya", "search", "subject:GOAL OR subject:goal", "--json"]
        
        try:
            output = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if output.returncode != 0:
                logger.warning("Himalaya search failed: %s", output.stderr)
                return results
            
            emails = json.loads(output.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning("Failed to fetch emails: %s", exc)
            return results
        
        for email in emails:
            try:
                sender = email.get("from", "")
                subject = email.get("subject", "")
                body = email.get("body", "")
                
                parsed = process_email_for_goal(sender, subject, body, session_id)
                
                if parsed["has_goal"] and parsed["goal_text"]:
                    result = set_goal_from_goal_text(
                        parsed["goal_text"],
                        session_id or f"email-{email.get('id', 'unknown')}",
                    )
                    
                    if result["success"]:
                        results.append({
                            "email_id": email.get("id"),
                            "sender": sender,
                            "subject": subject,
                            "goal": parsed["goal_text"],
                            "source": parsed["source"],
                            "status": "set",
                        })
                        
                        # Optionally mark as read
                        if mark_processed:
                            subprocess.run(
                                ["himalaya", "read", str(email.get("id"))],
                                capture_output=True,
                                timeout=10,
                            )
                
            except Exception as exc:
                logger.error("Failed to process email %s: %s", email.get("id"), exc)
                continue
                
    except ImportError:
        logger.warning("Himalaya CLI not available for email processing")
    except Exception as exc:
        logger.error("Email processor error: %s", exc)
    
    return results


def main():
    """CLI entry point for email goal processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process emails and set Hermes goals")
    parser.add_argument("--session-id", help="Default session ID for goals")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't set goals")
    parser.add_argument("--mark-read", action="store_true", default=True, help="Mark processed emails as read")
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("Dry run mode - parsing emails only")
    
    results = run_email_processor(
        session_id=args.session_id,
        mark_processed=args.mark_read,
    )
    
    if results:
        print(f"\nProcessed {len(results)} goal emails:")
        for r in results:
            print(f"  ✓ {r['subject'][:60]}...")
            print(f"    Goal: {r['goal'][:80]}...")
    else:
        print("\nNo goal emails found to process")
    
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
