---
sidebar_position: 16
title: "Persistent Goals (`/goal`)"
description: "Set a standing goal and let Hermes keep working across turns until it's done. Our take on the Ralph loop."
---

# Persistent Goals (`/goal`)

`/goal` gives Hermes a standing objective that survives across turns. After every turn a lightweight judge model checks whether the goal is satisfied by the assistant's last response. If not, Hermes automatically feeds a continuation prompt back into the same session and keeps working — until the goal is achieved, you pause or clear it, or the turn budget runs out.

It's our take on the **Ralph loop**, directly inspired by [Codex CLI 0.128.0's `/goal`](https://github.com/openai/codex) by Eric Traut (OpenAI). The core idea — keep a goal alive across turns and don't stop until it's achieved — is theirs. The implementation here is independent and adapted to Hermes' architecture.

## When to use it

Use `/goal` for tasks where you want Hermes to iterate on its own without you re-prompting every turn:

- "Fix every lint error in `src/` and verify `ruff check` passes"
- "Port feature X from repo Y, including tests, and get CI green"
- "Investigate why session IDs sometimes drift on mid-run compression and write up a report"
- "Build a small CLI to rename files by their EXIF dates, then test it against the photos/ folder"

Tasks where the agent does one turn and stops don't need `/goal`. Tasks where *you'd otherwise have to say "keep going" three times* are where this shines.

## Quick start

```
/goal Fix every failing test in tests/hermes_cli/ and make sure scripts/run_tests.sh passes for that directory
```

What you'll see:

1. **Goal accepted** — `⊙ Goal set (20-turn budget): <your goal>`
2. **Turn 1 runs** — Hermes starts working as if you'd sent the goal as a normal message.
3. **Judge runs** — after the turn, the judge model decides `done` or `continue`.
4. **Loop fires if needed** — if `continue`, you'll see `↻ Continuing toward goal (1/20): <judge's reason>`. Hermes sends itself a continuation prompt and starts the next turn.
5. **Loop repeats** until the judge says `done`, you send a new message (which pauses the loop that turn), or you hit the turn budget.

## Commands

| Command | Description |
|---------|-------------|
| `/goal <text>` | Set a standing goal and kick off the first turn immediately |
| `/goal` or `/goal status` | Show the active goal, turn count, and state (active/paused) |
| `/goal pause` | Pause the loop — Hermes will keep judging but won't auto-continue |
| `/goal resume` | Resume from paused, resets turn counter to 0 |
| `/goal clear` | Drop the goal entirely |

All commands work on CLI and gateway (Slack, Telegram, Discord, etc.).

## How it works

### The judge model

Every time the agent finishes a turn (final response delivered), a small auxiliary-model call runs:

```
Is the user's goal fully satisfied by the assistant's response above?
Goal: {goal_text}
Respond with JSON only: {"done": true|false, "reason": "..."}
```

The **default judge** is the configured auxiliary model. You can override per-task:

```yaml
# ~/.hermes/config.yaml
auxiliary:
  goal_judge: "openai/gpt-4o-mini"  # cheap, fast, good enough
```

### Fail-open semantics

If the judge returns malformed JSON, times out, or raises, the loop **continues** (`fail-open`). A flaky judge can't wedge you in an endless loop — the **turn budget** is the real backstop.

### Turn budget (default 20)

`goals.max_turns` caps how many automatic continuations Hermes will fire before pausing and asking you to `/goal resume`.

```yaml
# ~/.hermes/config.yaml
goals:
  max_turns: 30  # bump for fuzzier / multi-step goals
```

Budget exhaustion shows:
```
⏸ Goal paused (budget exhausted at 20/20 turns): <goal>
Type /goal resume to continue, or /goal clear to drop it.
```

### Preemption by user messages

If you send a real message while a goal is active, it **preempts** the continuation prompt — your message runs first, then the judge re-evaluates. You're always in control.

### Session persistence

Goal state (text, turn count, paused/active) lives in `SessionDB.state_meta` keyed by `goal:<session_id>`. If you `/stop` and `/resume` a named session, the goal comes back exactly as you left it.

### Prompt caching

Continuation prompts are just **user-role messages** appended to history. There's no system-prompt mutation and no toolset swap — providers that cache the prompt prefix (Anthropic, OpenAI with `prompt_cache`) keep their cache intact across turns.

## Configuration

See [Configuration](../../configuration.md) for auxiliary model settings and [Auxiliary Models](../../configuration.md#auxiliary-models) for the `goal_judge` override.

```yaml
# ~/.hermes/config.yaml
goals:
  max_turns: 20

auxiliary:
  goal_judge: "openai/gpt-4o-mini"  # optional per-task override
```

## Walkthrough example

**User:**
```
/goal Refactor the retry logic in tools/web_tools.py to use tenacity instead of hand-rolled exponential backoff
```

**Hermes:**
```
⊙ Goal set (20-turn budget): Refactor the retry logic...
I'll keep working until the goal is done, you pause/clear it, or the budget is exhausted.
Controls: /goal status · /goal pause · /goal resume · /goal clear
```

**[Turn 1 runs, agent refactors web_tools.py]**

**Judge:**
```
↻ Continuing toward goal (1/20): Retry logic refactored but tests haven't been updated yet.
```

**[Turn 2 runs, agent updates tests]**

**Judge:**
```
↻ Continuing toward goal (2/20): Tests updated but CI hasn't been verified.
```

**[Turn 3 runs, agent runs CI via terminal]**

**Judge:**
```
✓ Goal achieved (3/20 turns): tenacity integration complete, tests pass, CI green.
```

Loop stops. Session continues normally.

## Recovering from failures

### False positive (judge says done when it isn't)

The judge may be too conservative. If it claims "done" prematurely:

1. Send a follow-up message explaining what's still missing.
2. The goal is still active — judge will re-run next turn.
3. Or `/goal clear` then `/goal <refined goal>` with a clearer success criteria.

### False negative (judge says continue when it's done)

If the budget runs out on a goal that was actually finished a few turns ago:

```
⏸ Goal paused (budget exhausted at 20/20 turns): ...
```

Either `/goal resume` to keep going with a refreshed counter, or just send a normal message — the work is done.

### Debugging

Set verbose logging to see judge prompts and responses:

```bash
hermes config set logging.level debug
```

Look for:
- `goal: evaluating` — judge call starting
- `goal: judge response` — raw model output
- `goal continuation: ...` — enqueueing next turn

## Prior art

- **Codex CLI 0.128.0's `/goal`** — [github.com/openai/codex](https://github.com/openai/codex), built by [Eric Traut](https://github.com/erictraut) (Pyright author on the Codex team). This is the direct inspiration for the Ralph-loop pattern.

## Troubleshooting

**`/goal shows "Goals unavailable"`**  
Goals require an active session. If you just started Hermes or used `/new`, set a session name first (`/goal` works with named sessions).

**"Agent is running — wait or /stop" when setting a goal**  
You can't set a new goal while the agent is mid-turn. Use `/goal status/pause/clear` mid-run, or `/stop` then `/goal <text>`.

**Loop feels too aggressive / too conservative**  
Override the judge model in config. Smaller/cheaper models are more aggressive; larger models are more conservative.
