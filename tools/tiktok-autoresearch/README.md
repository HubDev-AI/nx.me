# TikTok Autoresearch

Autonomous content generation loop for NXME's TikTok marketing. Applies [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) pattern (43K stars, March 2026) to content creation instead of ML training.

## How to run

```bash
cd tools/tiktok-autoresearch
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# Quick test -- 2 hook iterations
python run.py hooks -n 2

# Overnight mode -- run everything
python run.py all

# Just hooks, 50 iterations
python run.py hooks

# Lower the keep threshold to capture more ideas
python run.py hooks -t 6 -n 100
```

### Content types

| Command | What it generates | Default iterations |
|---------|------------------|--------------------|
| `hooks` | First 1-3 second TikTok hooks | 50 |
| `captions` | Captions + hashtag combos | 30 |
| `calendar` | Content calendar slots | 5 |
| `trends` | Trend-to-NXME content concepts | 40 |
| `competitors` | Competitor teardowns + adaptations | 10 |
| `all` | All of the above, sequentially | varies |

## How it works

Exactly like Karpathy's autoresearch loop:

1. Reads `strategy.md` (your `program.md`)
2. Calls Claude Sonnet in a loop
3. Each iteration: generates content + self-scores it (1-10 rubric)
4. Score >= threshold --> keep, below --> discard
5. Top 3 kept results feed back as context (the "current best to beat")
6. Outputs: TSV (all iterations) + markdown (ranked best results)

### Cost estimate

~$0.03-0.10 per iteration depending on content type. 50 hook iterations ~$2-3. Full `all` run ~$10-15.

## What autoresearch actually is

Karpathy's autoresearch (43K stars, created March 6, 2026) is an autonomous AI experimentation harness for ML training. The core loop:

1. Human writes `program.md` -- strategy, constraints, goals, metric
2. Agent edits `train.py` -- the single file it can modify
3. Runs a 5-minute experiment --> reads `val_bpb` (validation bits per byte)
4. If improved --> keep (advance branch). If worse --> discard (`git reset`)
5. **NEVER STOP** -- loops indefinitely until human interrupts

### Key design principles

- **Single metric** (`val_bpb`) -- no ambiguity about what "better" means
- **Fixed time budget** (5 min) -- makes all experiments directly comparable
- **Single file scope** -- agent only touches `train.py`, everything else is locked
- **Git-based state** -- keep = commit stays, discard = git reset
- **Human writes strategy, agent executes** -- `program.md` is the human's lever

## How this maps to TikTok marketing

The repo itself is a GPU training harness -- it won't analyze TikTok. But the architecture pattern transfers directly. Here's how each content type maps:

### Hooks (highest value)

TikTok's algorithm lives and dies in the first 1-3 seconds. This is your `train.py`.

The loop explores different hook archetypes: question, POV, challenge, hot take, tutorial tease, transformation reveal. Run overnight, wake up to 50+ ranked hooks ready to film.

### Trends

Fixed time budget per trend (the autoresearch insight that makes experiments comparable). Each iteration: pull a trending concept, assess relevance to NXME's pillars, draft a content concept, score fit, keep or discard.

### Competitors

Maps the "read state --> hypothesize --> test --> evaluate" pattern to competitor analysis. Reviews top competitor content, extracts patterns, generates NXME-adapted versions, scores fit.

### Captions + hashtags

Identical to the ML loop: generate caption + hashtag combo, score against TikTok SEO signals, keep if better than current best.

### Content calendar

Generates a balanced posting schedule across content pillars (education, transformation, trend, UGC) with hook + concept for each slot.

## The meta-insight

Karpathy's key quote: *"You are not touching any of the Python files like you normally would as a researcher. Instead, you are programming the program.md Markdown files."*

Translated for marketing: stop being a content creator, become a content strategist who programs agents. Your job shifts from "write 50 hooks" to "write the brief that generates 500 hooks and scores the best 50."

The principles that transfer:

- **Single clear metric** -- define what "good" means numerically before the loop starts
- **Fixed budget per iteration** -- prevents rabbit holes, makes experiments comparable
- **Keep/discard discipline** -- no sunk cost fallacy
- **NEVER STOP** -- the agent runs while you sleep/film/edit
- **Human writes strategy, agent executes volume** -- you own `strategy.md`, the agent owns the iterations

## Customization

Edit `strategy.md` to change brand voice, target audience, content pillars, or constraints. The agent reads it before every iteration. Edit prompt files in `prompts/` to change the generation instructions per content type.
