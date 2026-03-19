# NXME Marketing Tools

AI-powered marketing tools for NXME's TikTok growth strategy. Each tool applies autonomous AI loop patterns to a different phase of content marketing.

## Tools

### [tiktok-autoresearch](./tiktok-autoresearch/)

**Content generation engine.** Applies Karpathy's autoresearch loop to produce ranked TikTok content — hooks, captions, hashtags, content calendars, trend analysis, and competitor teardowns.

**Use when:** You need actual content to post. Daily content production.

```bash
cd tools/tiktok-autoresearch
python run.py hooks -n 50
```

### [mirofish-simulator](./mirofish-simulator/)

**Strategy prediction engine.** Uses MiroFish multi-agent simulation to predict audience reactions to different content strategies before you execute them. Simulates thousands of virtual users with distinct personalities reacting to your campaigns.

**Use when:** Planning campaigns, choosing launch strategy, preparing for crises.

```bash
cd /Users/vladimirtrifonov/src/ai/MiroFish
./start.sh
# Open http://localhost:3000
```

## Recommended workflow

```
MiroFish (predict) -> Autoresearch (produce) -> TikTok (publish) -> Analytics (measure) -> repeat
```

1. **Predict** — Run MiroFish simulation to choose strategy
2. **Produce** — Feed winning strategy into autoresearch `strategy.md`, generate content
3. **Publish** — Post top-ranked content to TikTok
4. **Measure** — Check TikTok Analytics for real performance
5. **Iterate** — Feed real data back into MiroFish for next cycle
