#!/usr/bin/env python3
"""knowledge-extract: retroactive Panning for Gold over past session transcripts.

Reads JSONL transcripts, sends condensed conversation to Haiku, extracts:
- Atomic knowledge notes (findings, decisions, corrections)
- Reference candidates (patterns, recurring facts worth maintaining)
- Research report candidates (sessions with external source synthesis)

Outputs to stdout for review (calibration mode) or writes to vault (commit mode).

Usage:
    # Calibration: preview extractions without writing
    python3 knowledge-extract.py --transcript <path.jsonl> --config conservative
    python3 knowledge-extract.py --transcript <path.jsonl> --config aggressive

    # Batch: process all unextracted transcripts and write to vault
    python3 knowledge-extract.py --vault ~/ashco-vault --device-id mini --commit
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CONSERVATIVE_PROMPT = """You are extracting durable knowledge from a Claude Code session transcript.
Be selective. Only extract findings that would be useful in a FUTURE session (not just this one).

Session info:
- Duration: {duration}
- User turns: {user_turns}

Transcript (condensed):
{conversation}

Extract the following categories. For each item, output a JSON object on its own line.
If a category has no items, skip it entirely. Prefer fewer high-quality items over many weak ones.

Categories:
1. ATOMIC: individual findings, decisions, or corrections. A fact someone would want to recall later.
   {{"category": "atomic", "title": "...", "content": "...", "tags": ["...", "..."], "domain": "...", "confidence": "high|medium|low"}}

2. REFERENCE_CANDIDATE: a pattern or recurring fact worth maintaining as a reference doc.
   Only extract if the session reveals something that should be checked/updated regularly.
   {{"category": "reference", "title": "...", "content": "...", "tags": ["...", "..."], "domain": "..."}}

3. RESEARCH: if this session involved researching an external topic (reading articles, comparing approaches,
   investigating a technology), summarize the research findings.
   {{"category": "research", "title": "...", "content": "...", "tags": ["...", "..."], "domain": "...", "topic": "...", "sources_consulted": ["..."]}}

Rules:
- Skip ephemeral state (what's blocked, what's next). That belongs in hot.md, not knowledge.
- Skip things derivable from code or git history (file paths, commit hashes, what changed).
- Skip behavioral preferences (those go through codify, not knowledge extraction).
- Each item's content should be 2-5 sentences, self-contained, understandable without the transcript.
- Use [[wikilinks]] when referencing known projects or concepts.
- Tags: 3-5 lowercase kebab-case topical tags per item.
- Confidence: high = verified fact, medium = likely correct but not tested, low = speculation.
- Output ONLY the JSON lines. No markdown, no headers, no explanation."""

AGGRESSIVE_PROMPT = """You are extracting knowledge from a Claude Code session transcript.
Cast a wide net. Extract anything that might be useful in a future session, even if marginal.

Session info:
- Duration: {duration}
- User turns: {user_turns}

Transcript (condensed):
{conversation}

Extract the following categories. For each item, output a JSON object on its own line.

Categories:
1. ATOMIC: any finding, decision, correction, discovery, or non-obvious fact from the session.
   {{"category": "atomic", "title": "...", "content": "...", "tags": ["...", "..."], "domain": "...", "confidence": "high|medium|low"}}

2. REFERENCE_CANDIDATE: patterns, recurring data, or maintained facts worth tracking.
   {{"category": "reference", "title": "...", "content": "...", "tags": ["...", "..."], "domain": "..."}}

3. RESEARCH: any external topic investigated, technology evaluated, or approach compared.
   {{"category": "research", "title": "...", "content": "...", "tags": ["...", "..."], "domain": "...", "topic": "...", "sources_consulted": ["..."]}}

Rules:
- Each item's content should be 2-5 sentences, self-contained.
- Use [[wikilinks]] when referencing known projects or concepts.
- Tags: 3-5 lowercase kebab-case topical tags per item.
- Output ONLY the JSON lines. No markdown, no headers, no explanation."""

SYSTEM_NOISE = [
    "<local-command-caveat>",
    "<system-reminder>",
    "<command-name>",
    "Contents of /Users/",
    "CONTEXT\n=======",
]

NOISE_PATH_PATTERNS = [
    "/.claude/plugins/cache/",
    "/.claude/skills/",
    "/.config/superpowers/",
]

SKIP_PROJECT_PATTERNS = [
    "-workers-reader-sync",
    "-workers-scheduled-scripts",
]


def extract_conversation(jsonl_path: str, max_chars: int = 15000) -> dict | None:
    """Parse a JSONL transcript into a condensed conversation string."""
    user_messages = []
    assistant_messages = []
    all_timestamps = []

    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = obj.get("timestamp")
                if ts:
                    all_timestamps.append(ts)

                msg = obj.get("message")
                if not isinstance(msg, dict):
                    if obj.get("type") == "user" and isinstance(obj.get("content"), str):
                        text = obj["content"]
                        if text and len(text) > 1:
                            user_messages.append(text)
                    continue

                role = msg.get("role")
                content = msg.get("content")

                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                    text = "\n".join(parts)
                else:
                    text = ""

                if role == "user":
                    if isinstance(content, list) and all(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    ):
                        continue
                    if text.strip():
                        user_messages.append(text.strip())
                elif role == "assistant":
                    if text.strip():
                        assistant_messages.append(text.strip())
    except Exception as e:
        print(f"  [error] Failed to parse {jsonl_path}: {e}", file=sys.stderr)
        return None

    if len(user_messages) < 3:
        return None

    # Compute duration
    duration = "unknown"
    if len(all_timestamps) >= 2:
        try:
            t0 = datetime.fromisoformat(all_timestamps[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(all_timestamps[-1].replace("Z", "+00:00"))
            mins = int((t1 - t0).total_seconds() / 60)
            if mins < 60:
                duration = f"{mins} min"
            else:
                duration = f"{mins // 60}h {mins % 60}m"
        except (ValueError, TypeError):
            pass

    # Build condensed conversation (interleave user/assistant, cap at max_chars)
    convo_lines = []
    char_count = 0
    max_per_msg = 600

    all_turns = []
    for msg in user_messages:
        cleaned = msg
        if any(pat in cleaned for pat in SYSTEM_NOISE):
            cleaned = re.sub(r"<[^>]+>[^<]*</[^>]+>", "", cleaned)
            cleaned = re.sub(r"<[^>]+>", "", cleaned)
            cleaned = re.sub(r"CONTEXT\s*\n=+\n.*", "", cleaned, flags=re.DOTALL)
            cleaned = re.sub(r"Contents of /Users/\S+:.*?(?=\n\n|\Z)", "", cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip()
        if len(cleaned) > 5:
            all_turns.append(("USER", cleaned[:max_per_msg]))

    for msg in assistant_messages:
        if len(msg) > 5:
            all_turns.append(("ASST", msg[:max_per_msg]))

    for role, text in all_turns:
        chunk = f"{role}: {text}"
        if char_count + len(chunk) > max_chars:
            break
        convo_lines.append(chunk)
        char_count += len(chunk)

    return {
        "conversation": "\n\n".join(convo_lines),
        "user_turns": len(user_messages),
        "duration": duration,
        "first_ts": all_timestamps[0] if all_timestamps else None,
    }


def extract_knowledge(conversation_data: dict, config: str, api_key: str, base_url: str | None = None) -> list[dict]:
    """Send transcript to Haiku, parse JSON-line extractions."""
    prompt_template = CONSERVATIVE_PROMPT if config == "conservative" else AGGRESSIVE_PROMPT

    prompt = prompt_template.format(
        duration=conversation_data["duration"],
        user_turns=conversation_data["user_turns"],
        conversation=conversation_data["conversation"],
    )

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
    except Exception as e:
        print(f"  [error] Haiku extraction failed: {e}", file=sys.stderr)
        return []

    items = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
            if "category" in item and "title" in item:
                items.append(item)
        except json.JSONDecodeError:
            continue

    return items


def format_preview(items: list[dict], config: str, transcript_path: str) -> str:
    """Format extracted items for human review."""
    lines = [
        f"## Config: {config}",
        f"Transcript: {os.path.basename(transcript_path)}",
        f"Items extracted: {len(items)}",
        "",
    ]

    by_category = {}
    for item in items:
        cat = item.get("category", "unknown")
        by_category.setdefault(cat, []).append(item)

    for cat, cat_items in sorted(by_category.items()):
        lines.append(f"### {cat.upper()} ({len(cat_items)})")
        lines.append("")
        for item in cat_items:
            lines.append(f"**{item.get('title', 'untitled')}**")
            lines.append(f"  {item.get('content', '')}")
            tags = item.get("tags", [])
            if tags:
                lines.append(f"  tags: {', '.join(tags)}")
            conf = item.get("confidence")
            if conf:
                lines.append(f"  confidence: {conf}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract knowledge from Claude Code transcripts")
    parser.add_argument("--transcript", help="Single transcript to process (calibration mode)")
    parser.add_argument("--config", choices=["conservative", "aggressive"], default="conservative")
    parser.add_argument("--vault", default=os.path.expanduser("~/ashco-vault"))
    parser.add_argument("--device-id", default=os.environ.get("VAULT_DEVICE_ID", "default"))
    parser.add_argument("--commit", action="store_true", help="Write to vault and git commit (not just preview)")
    parser.add_argument("--both", action="store_true", help="Run both configs side-by-side (calibration)")
    args = parser.parse_args()

    proxy_url = os.environ.get("CLAUDE_PROXY_URL", "")
    proxy_key = os.environ.get("CLAUDE_PROXY_API_KEY", "")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    base_url = None
    if proxy_url and proxy_key:
        base_url = proxy_url
        llm_key = proxy_key
    elif api_key:
        llm_key = api_key
    else:
        print("Error: set CLAUDE_PROXY_URL+CLAUDE_PROXY_API_KEY or ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    if args.transcript:
        convo = extract_conversation(args.transcript)
        if not convo:
            print("Could not parse transcript (too short or unreadable)")
            sys.exit(1)

        if args.both:
            for cfg in ["conservative", "aggressive"]:
                items = extract_knowledge(convo, cfg, llm_key, base_url)
                print(format_preview(items, cfg, args.transcript))
                print("=" * 60)
        else:
            items = extract_knowledge(convo, args.config, llm_key, base_url)
            print(format_preview(items, args.config, args.transcript))
    else:
        print("Batch mode not yet implemented. Use --transcript for calibration.")


if __name__ == "__main__":
    main()
