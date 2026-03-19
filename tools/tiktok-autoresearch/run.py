#!/usr/bin/env python3
"""
TikTok Autoresearch — Autonomous content generation loop for NXME.

Applies Karpathy's autoresearch pattern to TikTok marketing:
human writes strategy.md, agent generates + scores + keeps/discards content.

Usage:
    python run.py hooks --iterations 50
    python run.py captions --iterations 30
    python run.py calendar --iterations 5
    python run.py trends --iterations 40
    python run.py competitors --iterations 10
    python run.py all
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
STRATEGY_PATH = SCRIPT_DIR / "strategy.md"
PROMPTS_DIR = SCRIPT_DIR / "prompts"
RESULTS_DIR = SCRIPT_DIR / "results"

CONTENT_TYPES = {
    "hooks": {"prompt_file": "hooks.txt", "default_iterations": 50, "keep_threshold": 8},
    "captions": {"prompt_file": "captions.txt", "default_iterations": 30, "keep_threshold": 7},
    "calendar": {"prompt_file": "calendar.txt", "default_iterations": 5, "keep_threshold": 7},
    "trends": {"prompt_file": "trends.txt", "default_iterations": 40, "keep_threshold": 7},
    "competitors": {"prompt_file": "competitors.txt", "default_iterations": 10, "keep_threshold": 7},
}

DEFAULT_MODEL = "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# File loaders
# ---------------------------------------------------------------------------

def load_strategy() -> str:
    """Load the strategy.md file — the human's lever."""
    if not STRATEGY_PATH.exists():
        print(f"ERROR: {STRATEGY_PATH} not found. Create it first.")
        sys.exit(1)
    return STRATEGY_PATH.read_text()


def load_prompt(content_type: str) -> str:
    """Load the type-specific prompt template."""
    cfg = CONTENT_TYPES[content_type]
    prompt_path = PROMPTS_DIR / cfg["prompt_file"]
    if not prompt_path.exists():
        print(f"ERROR: {prompt_path} not found.")
        sys.exit(1)
    return prompt_path.read_text()


# ---------------------------------------------------------------------------
# Results management
# ---------------------------------------------------------------------------

def get_results_paths(content_type: str, run_id: str) -> tuple[Path, Path]:
    """Return (tsv_path, best_md_path) for a run."""
    tsv_path = RESULTS_DIR / f"{content_type}_{run_id}.tsv"
    best_path = RESULTS_DIR / f"{content_type}_{run_id}_best.md"
    return tsv_path, best_path


def init_tsv(tsv_path: Path) -> None:
    """Create TSV with header row."""
    with open(tsv_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["iteration", "score", "status", "content", "reasoning"])


def append_tsv(tsv_path: Path, iteration: int, score: float, status: str,
               content: str, reasoning: str) -> None:
    """Append one row to the results TSV."""
    with open(tsv_path, "a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        # Collapse newlines in content/reasoning for TSV compatibility
        content_flat = content.replace("\n", " | ").replace("\t", " ")
        reasoning_flat = reasoning.replace("\n", " ").replace("\t", " ")
        writer.writerow([iteration, f"{score:.1f}", status, content_flat, reasoning_flat])


def load_kept_results(tsv_path: Path) -> list[dict]:
    """Load kept results from existing TSV for resume support."""
    if not tsv_path.exists():
        return []
    kept = []
    with open(tsv_path, "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("status") == "keep":
                kept.append(row)
    return kept


def write_best_markdown(best_path: Path, content_type: str, kept: list[dict]) -> None:
    """Write a curated markdown file of the best results."""
    if not kept:
        best_path.write_text(f"# {content_type.title()} — No results kept\n\nAll iterations scored below threshold.\n")
        return

    # Sort by score descending
    sorted_kept = sorted(kept, key=lambda r: float(r.get("score", 0)), reverse=True)

    lines = [
        f"# {content_type.title()} — Best Results",
        f"\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Total kept: {len(sorted_kept)}",
        "",
    ]

    for i, row in enumerate(sorted_kept, 1):
        lines.append(f"## #{i} (Score: {row['score']})")
        lines.append("")
        lines.append(row.get("content", ""))
        lines.append("")
        if row.get("reasoning"):
            lines.append(f"*{row['reasoning']}*")
            lines.append("")
        lines.append("---")
        lines.append("")

    best_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def build_user_message(content_type: str, iteration: int, total: int,
                       top_results: list[dict]) -> str:
    """Build the user message for each iteration."""
    msg = f"Iteration {iteration}/{total}.\n\n"

    if top_results:
        msg += "Current top results to beat:\n\n"
        for i, r in enumerate(top_results[:3], 1):
            msg += f"{i}. (Score {r['score']}) {r['content'][:200]}\n"
        msg += "\nGenerate something DIFFERENT and try to beat these scores.\n"
    else:
        msg += "This is the first iteration. Set a strong baseline.\n"

    msg += f"\nRemember: respond with ONLY valid JSON. No markdown fences, no explanation outside the JSON."
    return msg


def extract_content_summary(content_type: str, data: dict) -> str:
    """Extract a human-readable content summary from the parsed JSON."""
    if content_type == "hooks":
        return data.get("hook_text", json.dumps(data)[:200])
    elif content_type == "captions":
        caption = data.get("caption", "")
        tags = " ".join(data.get("hashtags", []))
        return f"{caption} {tags}"
    elif content_type == "calendar":
        entries = data.get("calendar", [])
        return f"{len(entries)}-day calendar: " + " | ".join(
            f"D{e.get('day', '?')}: {e.get('pillar', '?')}" for e in entries[:5]
        ) + ("..." if len(entries) > 5 else "")
    elif content_type == "trends":
        return f"[{data.get('trend_type', '?')}] {data.get('trend_name', '?')}: {data.get('nxme_angle', '')[:150]}"
    elif content_type == "competitors":
        return f"{data.get('competitor_name', '?')}: {data.get('content_strategy_summary', '')[:150]}"
    return json.dumps(data)[:200]


def run_loop(content_type: str, iterations: int, model: str, run_id: str) -> None:
    """Run the autoresearch loop for a given content type."""
    strategy = load_strategy()
    prompt = load_prompt(content_type)
    cfg = CONTENT_TYPES[content_type]
    threshold = cfg["keep_threshold"]

    tsv_path, best_path = get_results_paths(content_type, run_id)

    # Resume support: load existing kept results
    kept = load_kept_results(tsv_path)
    start_iteration = len(load_kept_results(tsv_path)) + 1 if tsv_path.exists() else 1

    if start_iteration == 1:
        init_tsv(tsv_path)
        print(f"\n{'='*60}")
        print(f"  {content_type.upper()} — {iterations} iterations")
        print(f"  Model: {model}")
        print(f"  Keep threshold: {threshold}/10")
        print(f"  Results: {tsv_path}")
        print(f"{'='*60}\n")
    else:
        print(f"\n  Resuming {content_type} from iteration {start_iteration} ({len(kept)} kept so far)")

    client = anthropic.Anthropic()

    system_message = f"""You are an autonomous TikTok content researcher for NXME.

## Brand Strategy
{strategy}

## Your Task
{prompt}"""

    kept_count = len(kept)
    discarded_count = 0

    for i in range(start_iteration, start_iteration + iterations):
        # Build top results for context (sorted by score, top 3)
        top_results = sorted(kept, key=lambda r: float(r.get("score", 0)), reverse=True)[:3]

        user_msg = build_user_message(content_type, i, start_iteration + iterations - 1, top_results)

        try:
            t0 = time.time()
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_message,
                messages=[{"role": "user", "content": user_msg}],
            )
            elapsed = time.time() - t0

            # Parse response
            raw_text = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                # Remove first and last lines (fences)
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw_text = "\n".join(lines)

            data = json.loads(raw_text)
            score = float(data.get("total_score", 0))
            reasoning = data.get("reasoning", "")
            content_summary = extract_content_summary(content_type, data)

            # Keep or discard
            if score >= threshold:
                status = "keep"
                kept_count += 1
                kept.append({"score": str(score), "content": content_summary, "reasoning": reasoning})
                symbol = "+"
            else:
                status = "discard"
                discarded_count += 1
                symbol = "-"

            append_tsv(tsv_path, i, score, status, content_summary, reasoning)
            print(f"  [{symbol}] #{i:3d}  score={score:4.1f}  {status:7s}  ({elapsed:.1f}s)  {content_summary[:80]}")

        except json.JSONDecodeError as e:
            append_tsv(tsv_path, i, 0, "error", f"JSON parse error: {e}", raw_text[:200] if 'raw_text' in dir() else "")
            discarded_count += 1
            print(f"  [!] #{i:3d}  JSON parse error — discarded")

        except anthropic.APIError as e:
            append_tsv(tsv_path, i, 0, "error", f"API error: {e}", "")
            discarded_count += 1
            print(f"  [!] #{i:3d}  API error: {e}")
            # Back off on rate limits
            if "rate" in str(e).lower():
                print("      Rate limited — waiting 30s...")
                time.sleep(30)

        except KeyboardInterrupt:
            print(f"\n\n  Interrupted at iteration {i}. Results saved.")
            break

    # Write best results markdown
    write_best_markdown(best_path, content_type, kept)

    print(f"\n  Done: {kept_count} kept, {discarded_count} discarded")
    print(f"  Results: {tsv_path}")
    print(f"  Best:    {best_path}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="TikTok Autoresearch — autonomous content generation loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Content types:
  hooks        Generate and score TikTok hooks (first 1-3 seconds)
  captions     Generate caption + hashtag combinations
  calendar     Generate 2-week content calendars
  trends       Match current trends to NXME content angles
  competitors  Tear down competitor content strategies
  all          Run all content types sequentially
        """,
    )
    parser.add_argument(
        "type",
        choices=list(CONTENT_TYPES.keys()) + ["all"],
        help="Content type to generate",
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=None,
        help="Number of iterations (default varies by type)",
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"Anthropic model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=int,
        default=None,
        help="Score threshold for keeping results (default varies by type)",
    )

    args = parser.parse_args()

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Generate run ID from timestamp
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Determine which types to run
    if args.type == "all":
        types_to_run = list(CONTENT_TYPES.keys())
    else:
        types_to_run = [args.type]

    # Override threshold if specified
    if args.threshold is not None:
        for t in types_to_run:
            CONTENT_TYPES[t]["keep_threshold"] = args.threshold

    print(f"\nTikTok Autoresearch — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Strategy: {STRATEGY_PATH}")
    print(f"Model: {args.model}")

    for content_type in types_to_run:
        iters = args.iterations or CONTENT_TYPES[content_type]["default_iterations"]
        run_loop(content_type, iters, args.model, run_id)

    print("All runs complete.")


if __name__ == "__main__":
    main()
