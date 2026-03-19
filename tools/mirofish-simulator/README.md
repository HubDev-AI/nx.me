# MiroFish Simulator — NXME Marketing Strategy Predictor

Multi-agent social simulation for predicting TikTok audience reactions before you post. Uses [MiroFish](https://github.com/666ghj/MiroFish) (AI prediction engine based on Karpathy-style autonomous agents) to simulate thousands of virtual users reacting to different content strategies.

## What this does vs. the autoresearch tool

| Tool                    | Purpose                                        | When to use                                     |
| ----------------------- | ---------------------------------------------- | ----------------------------------------------- |
| **mirofish-simulator**  | Predict which strategy wins before you execute | Campaign planning, launch strategy, crisis prep |
| **tiktok-autoresearch** | Generate and score actual content              | Daily content production                        |

MiroFish answers "what should we do?" — autoresearch answers "how do we do it well?"

## Setup

### Prerequisites

- Docker installed and running
- Anthropic API key (`ANTHROPIC_API_KEY` env var)
- Zep Cloud API key (free at https://app.getzep.com/)

### Installation

Clone the MiroFish repo at `./tools/mirofish-simulator/MiroFish`. All NXME-specific configuration is already in place.

```bash
# 1. Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# 2. Launch (starts LiteLLM proxy + MiroFish Docker)
cd /tools/mirofish-simulator/MiroFish
./start.sh

# 3. Open the UI
open http://localhost:3000
```

### Architecture

```
Your browser (localhost:3000)
    |
MiroFish Frontend (Vue, port 3000)
    |
MiroFish Backend (Flask, port 5001)
    |
LiteLLM Proxy (port 4000) ---- translates OpenAI SDK -> Anthropic API
    |
Claude Sonnet 4.6 (Anthropic)
    +
Zep Cloud (agent memory graphs)
```

MiroFish expects OpenAI SDK format. LiteLLM proxy runs locally and translates all calls to your Anthropic API key. No OpenAI account needed.

## How to run a simulation

### Step 1: Upload seed documents

In the MiroFish UI, upload the seed files from `tools/mirofish-simulator/nxme-seeds`:

| File                          | What it provides                                                       |
| ----------------------------- | ---------------------------------------------------------------------- |
| `tiktok-launch-simulation.md` | 3 launch strategies, 5 audience segments, 4 weekly scenario injections |
| `competitor-landscape.md`     | FaceApp/Lensa/YouCam positioning for agent awareness                   |

### Step 2: Enter your prediction query

Example queries to try:

**Strategy comparison (start here):**

> Simulate 30 days of NXME's TikTok launch. Compare Strategy A (curiosity-led: "what's my face shape?"), Strategy B (transformation-led: "before/after reveal"), and Strategy C (identity-preservation-led: "this actually looks like me"). Which strategy generates the highest engagement and most organic UGC?

**Crisis simulation:**

> NXME launched with Strategy B two weeks ago. A tech blogger publishes "AI beauty app rates your face — here's why that's toxic." Simulate how each audience segment reacts and what the optimal response strategy is.

**Influencer impact:**

> A micro-influencer with 50K followers posts a genuine positive reaction to NXME. Simulate the cascade effect across audience segments. Does it cross over from beauty to self-improvement audiences?

**Competitor response:**

> FaceApp launches a "style recommendations" feature similar to NXME. Simulate how this affects NXME's positioning and which content strategy best defends market position.

### Step 3: Configure simulation rounds

- Start with **20 rounds** for a quick read (~$5-10 in API costs)
- Use **40 rounds** for higher fidelity (~$10-20)
- Full multi-strategy comparison with all variables: ~$30-50

## Reading the results

MiroFish produces several output types:

### 1. Prediction Report

The main output. Contains:

- **Strategy rankings** — which approach wins on each metric (engagement, UGC, conversion signals, resilience)
- **Segment breakdowns** — how each audience persona (beauty enthusiasts, skeptics, content creators, etc.) responded
- **Timeline analysis** — how sentiment evolves over the simulated 30 days
- **Inflection points** — when and why the simulation shifted (e.g., "Week 3 influencer post caused 40% sentiment spike in self-improvement segment")

**What to look for:**

- Which strategy has the highest engagement-to-conversion ratio (not just raw engagement)
- Which audience segment becomes the strongest organic advocate
- How quickly negative sentiment spreads and through which segments

### 2. Agent Interaction Logs

Detailed records of what simulated agents "said" and "did." These read like social media comments and reactions.

**What to look for:**

- Common objections ("is this just another filter?") — these become FAQ/response templates
- Viral triggers ("I need to try this") — these become hook inspiration
- Drop-off points ("cool but I'm not paying") — these inform your free-to-paid funnel

### 3. Interactive Dialogue

After the simulation, you can talk directly to individual agents:

> "Agent #247 (beauty enthusiast, age 22): Why did you stop engaging after Week 2?"

> "Agent #891 (skeptic, age 28): What would have convinced you to download the app?"

This is the highest-value feature — it's like a focus group that runs in 10 minutes instead of 2 weeks.

**Best questions to ask agents:**

- "What was the moment you decided to try/skip the app?"
- "What would you tell a friend about NXME?"
- "What content would you create about this product?"
- "What's your biggest concern about this kind of app?"

### 4. Variable Injection Results

When you inject variables (competitor launch, negative press, influencer post), the report shows:

- **Before/after sentiment shift** per segment
- **Recovery time** — how many days until sentiment stabilizes
- **Best response action** — what the simulation suggests as optimal reaction

## NXME audience segments (pre-configured)

The seed document configures 5 agent populations:

| Segment                  | % of agents | Behavior pattern                                          | Key metric        |
| ------------------------ | ----------- | --------------------------------------------------------- | ----------------- |
| Beauty enthusiasts       | 40%         | High engagement, share transformations                    | UGC rate          |
| Self-improvement seekers | 25%         | Save content, pragmatic, moderate engagement              | Conversion intent |
| Skeptics                 | 15%         | Critical comments, demand proof, but convert if convinced | Sentiment shift   |
| Content creators         | 10%         | Try app for content, may create UGC                       | UGC creation rate |
| Casual scrollers         | 10%         | Passive, rarely engage                                    | Scroll-stop rate  |

## Workflow: MiroFish -> Autoresearch -> TikTok

The recommended full workflow:

```
1. MiroFish simulation
   -> "Strategy B (transformation-led) wins for engagement,
      but Strategy C (identity-preservation) is more resilient
      to negative press and converts skeptics better"

2. Update autoresearch strategy.md
   -> "Lead with transformation hooks but weave in
      identity-preservation messaging by Week 2"

3. Run autoresearch hooks/captions
   -> 50+ ranked hooks combining both angles

4. Film and post

5. Measure real TikTok analytics

6. Feed results back into MiroFish for next month's simulation
```

## Cost estimates

| Simulation type                          | Rounds | Estimated cost |
| ---------------------------------------- | ------ | -------------- |
| Quick strategy test                      | 20     | $5-10          |
| Full strategy comparison                 | 40     | $10-20         |
| Multi-strategy + all variables           | 60+    | $30-50         |
| Interactive agent dialogue (per session) | —      | $1-3           |

All costs are Claude Sonnet 4.6 API usage via Anthropic.

## Stopping

```bash
docker compose down
# Kill LiteLLM (PID shown at startup)
kill <litellm_pid>
```

## Files

All MiroFish files live at `tools/mirofish-simulator/nxme-seeds/MiroFish/`:

```
MiroFish/
  .env                          # API keys (Anthropic via LiteLLM + Zep)
  litellm-config.yaml           # LiteLLM proxy config
  start.sh                      # One-command launch
  NXME-SETUP.md                 # Detailed setup guide
  nxme-seeds/
    tiktok-launch-simulation.md # Main simulation scenario
    competitor-landscape.md     # Competitor knowledge base
```
