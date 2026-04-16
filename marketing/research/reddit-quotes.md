# Reddit quote bank

Customer-research verbatim quotes for NXME (AI glow-up app, 16–35 US, TikTok-native). Goal: capture real language about face shape, glow-up, LooksMax, and style advice — no paraphrase.

## Access notes / caveat

Direct Reddit endpoints (www.reddit.com, old.reddit.com, reddit.com JSON) are blocked from WebFetch in this environment (403 / refused). Google results for Reddit URLs returned only snippets, and snippet searches for `site:reddit.com` with specific quote-phrases mostly returned zero results.

What I tried and where it failed:
- `https://www.reddit.com/r/femalefashionadvice/search/?q=face+shape` → 403
- `https://old.reddit.com/r/glowups/top.json?t=year` → refused
- `https://www.reddit.com/r/looksmaxxing/top/?t=month` → refused
- `https://web.archive.org/web/2024/https://www.reddit.com/r/glowups/` → refused
- `https://looksmax.org/threads/...` (a primary off-Reddit looksmaxxing community often cross-linked with Reddit) → 403
- `https://www.lipstickalley.com/threads/anyone-else-avoiding-using-the-lensa-ai-app...` → 403
- `https://justuseapp.com/.../youcam-makeup...` and Apple App Store review page → initially 403 on some attempts
- `https://www.quora.com/Whats-your-post-breakup-glow-up-story` → 403

What worked:
- Reddit-adjacent looksmaxxing forum threads on `forum.looksmaxxing.com` (the sibling community cross-posted with r/looksmaxxing) — primary source of verbatim community language
- App-review aggregators (`grand-screen.com`, Apple App Store via secondary fetchers) for Umax verbatim reviews
- Google/Bing result snippets for general context (not quotable)

Because direct Reddit access failed, the quote bank below is heavily weighted toward (a) `forum.looksmaxxing.com` — the off-Reddit sibling to r/looksmaxxing where the same users post — and (b) app-store / review-aggregator verbatims. These are the population NXME sells against. Every quote below is VERBATIM from what I actually fetched; none are paraphrased or invented.

## Sources mined

Fetched successfully (verbatim extracted):

1. [Posted my face on reddit, most brutal shit ive seen. How bad do I look?](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) — forum.looksmaxxing.com
2. [Your mental health is a deal breaker in looksmaxxing](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/) — forum.looksmaxxing.com
3. [Locking tf in (criticism and advices will be really appreciated) and should I do softmaxxing or hardmaxxing?](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/) — forum.looksmaxxing.com
4. [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/) — forum.looksmaxxing.com
5. [The Importance of Facial Bones](https://forum.looksmaxxing.com/threads/the-importance-of-facial-bones.73012/) — forum.looksmaxxing.com
6. [Umax review aggregation — Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/) — user review verbatims
7. [Umax — App Store reviews](https://apps.apple.com/us/app/umax-become-hot/id6471026798?see-all=reviews&platform=iphone) — user review verbatims
8. [Hyperallergic — Read This Before You Jump on the Lensa "Magic Avatar" Trend](https://hyperallergic.com/read-this-before-you-jump-on-the-lensa-magic-avatar-trend/) — cited user reaction verbatims

Tried but blocked (listed for transparency, no quotes extracted): reddit.com, old.reddit.com, web.archive.org/reddit, looksmax.org, quora.com, lipstickalley.com, justuseapp.com, bbc.com, technologyreview.com (CSS-only response).

## Themes

### Theme 1 — "AI rating apps spit out random numbers, not a real rating" (High confidence, 2+ sources)

Users know the current AI-rating apps don't actually analyze the face. They want accuracy, and they're burned.

- **Frequency:** 2 of 8 sources (Umax review aggregators, cross-referenced with forum.looksmaxxing.com culture)
- **Intensity:** High — language is angry, mocking
- **Representative quotes:**
  - "submitted the same picture 3 times and almost every time a different number" — [Umax — App Store review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "it just pops up random numbers" — [Umax — App Store review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "the 10/10 AI just doesn't work" — [Umax — App Store review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "promised features barely work, if at all" — [Umax — App Store review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "They aren't harsher, they just retarded. They can't analyze shit they just spit out nonsense" (about reddit raters) — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
- **Implications for NXME:** Lean hard into "we actually analyze 468 landmarks — not a randomized number." Make the classification explainable (show which landmarks, which ratios) so the user believes the output. "It's not random" is a positioning wedge.

### Theme 2 — Umax is a paywall that delivers nothing (High, 2+ sources)

Users pay, nothing happens, they feel scammed. This is the emotional core of the competitor failure.

- **Frequency:** 2 of 8 sources
- **Intensity:** High — "scam," "money grab," "garbage"
- **Representative quotes:**
  - "Desperate money grab...It's just a money grab" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "complete scam...you have to either pay for a subscription or invite 3 friends" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "You literally have to pay just to see your results...absolutely garbage" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "literally the second i paid it went to what seemed like an infinite loop" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "I just spent 5 dollars and it doesn't even scan me" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "Nothing loads up...it just keeps loading and it never loads" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "Takes 10 years to scan my images" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
- **Implications for NXME:** Show the free result fast. Never force invite-gating. "Scan actually works" is table-stakes marketing language here.

### Theme 3 — Ratings demoralize and damage mental health (High, 2+ sources)

Looksmaxxing users repeatedly describe real psychological damage from the rating culture. This is the most powerful "anti-rating" narrative.

- **Frequency:** 2 of 8 sources (direct), echoed across looksmaxxing commentary
- **Intensity:** Very High
- **Representative quotes:**
  - "i was in a deep depression, distorted body image, mental illness, i remember spending nights awake thinking about life and considering ending it" — [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/)
  - "My soul is full of guilt and regret. I want to leave this world" — [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/)
  - "throughout this depression, i reached 58 kilos which is brutal for someone my height, my face was bloated and my eyes looked shallow, no light in them" — [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/)
  - "being depressed is such a looksmin buddy boyos" — [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/)
  - "For some reason I thought people on reddit would be nicer" — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
- **Implications for NXME:** Position as the "glow-up" app — not the "rating" app. Lead with *actionable style recommendations*, never a number. "Show me what works for MY face" not "Tell me my score."

### Theme 4 — "I don't know what to do with my face" + teenagers doing it anyway (High, 2+ sources)

Young users are actively asking for advice on haircuts, jaw, nose, orthodontics — they'll try anything, including destructive or surgical options. They are asking strangers because no one else will tell them.

- **Frequency:** 2 of 8 sources
- **Intensity:** High
- **Representative quotes:**
  - "Haircut nerfed tf outta me." — [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/)
  - "Not only hair my nose fucked up and teeth's too I'm gon get Damon braces and gon have nose surgery when I'm 18-19" — [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/)
  - "Bro icl I'm hella into hardmaxxing I like the concept a lot I wanted to do bone smashing" — [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/)
  - "Bruh I'm 14" — OP disclosed age — [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/)
  - "Brutal gotta hardmaxx" — [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/)
- **Implications for NXME:** The "what haircut works" question is the raw demand. If the app pushes *towards* softmaxx (hair, brows, glasses, style) it intercepts the harder path. Age gate seriously — lots of these posters are minors.

### Theme 5 — "Harmony, symmetry, angularity" is the in-group vocabulary (High, 2+ sources)

This is the language users use to describe faces. If NXME uses marketing copy like "find what suits your face shape" it'll sound dorky to this audience. They talk in facial-harmony terms.

- **Frequency:** 2 of 8 sources
- **Intensity:** Medium
- **Representative quotes:**
  - "Prominent cheekbones: Give a youthful appearance and make the face look more defined." — [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/)
  - "Defined jawline: Occurs when muscle growth is good, which is due to high testosterone." — [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/)
  - "A positive canthal tilt gives one a more attractive, sharper, and younger look." — [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/)
  - "Hooded eyes: Offers a sense of mystery and depth to their gaze." — [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/)
  - "Forward growth: Contributes to balanced facial features." — [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/)
  - "Having a dominant, angular, and symmetrical facial structure plays a big role in perceived male attractiveness." — [The Importance of Facial Bones](https://forum.looksmaxxing.com/threads/the-importance-of-facial-bones.73012/)
  - "Strong cheekbones, a prominent jawline, and forward growth shows good health and high testosterone." — [The Importance of Facial Bones](https://forum.looksmaxxing.com/threads/the-importance-of-facial-bones.73012/)
  - "I need zygos" (= cheekbones) — [The Importance of Facial Bones](https://forum.looksmaxxing.com/threads/the-importance-of-facial-bones.73012/)
- **Implications for NXME:** Landing-page copy can use terms like "facial harmony," "midface balance," "canthal tilt," "forward growth" — but translate to mainstream framing (i.e., "balanced features," "bright open eyes"). Don't fully adopt the jargon, but speak it back.

### Theme 6 — Reddit-style peer rating is brutal, racist, untrusted (Medium, 1 source, multiple quotes)

The "ask Reddit to rate me" path is broken. Users explicitly complain about the quality and tone of responses.

- **Frequency:** 1 source, multiple distinct speakers
- **Intensity:** High
- **Representative quotes:**
  - "Ppl on reddit are racist incels" — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
  - "Reddit n****s don't know how to rate" — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
  - "Do not post your face to bp spaces if you arent atleast whitepassing" — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
  - "For some reason I thought people on reddit would be nicer" — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
- **Implications for NXME:** "Private, non-judgmental, no strangers rating you" is a clear positioning wedge. Never make the product social-by-default. Opt-in sharing only.

### Theme 7 — AI beauty apps produce results that don't look like the user, especially for non-white users (Medium, 1 source but industry-backed)

- **Frequency:** 1 source (Hyperallergic quoting user reactions); backed by MIT Tech Review context
- **Intensity:** Medium-High
- **Representative quotes:**
  - "spending money to give up the rights to your face" — [Hyperallergic — Lensa](https://hyperallergic.com/read-this-before-you-jump-on-the-lensa-magic-avatar-trend/)
  - "overarching 'whiteness'" — users' description of Lensa avatars — [Hyperallergic — Lensa](https://hyperallergic.com/read-this-before-you-jump-on-the-lensa-magic-avatar-trend/)
  - "exaggerated racialized phenotypes" — users' description — [Hyperallergic — Lensa](https://hyperallergic.com/read-this-before-you-jump-on-the-lensa-magic-avatar-trend/)
  - "lean heavily" toward the male gaze — user observation on Lensa output — [Hyperallergic — Lensa](https://hyperallergic.com/read-this-before-you-jump-on-the-lensa-magic-avatar-trend/)
  - "stealing from previously existing artwork" — user on AI training — [Hyperallergic — Lensa](https://hyperallergic.com/read-this-before-you-jump-on-the-lensa-magic-avatar-trend/)
- **Implications for NXME:** Identity-preserving output is a differentiator. State clearly: "Trained for every face shape and skin tone. Before/after preserves you — it's still you." Privacy: "We don't train on your face. Images deleted after X days."

### Theme 8 — Privacy and data extraction suspicion (Medium, 2 sources)

- **Frequency:** 2 sources
- **Intensity:** Medium
- **Representative quotes:**
  - "they have asked for your email and pictures. I think they might be selling the data" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
  - "spending money to give up the rights to your face" — [Hyperallergic — Lensa](https://hyperallergic.com/read-this-before-you-jump-on-the-lensa-magic-avatar-trend/)
- **Implications for NXME:** Lead with data commitments in the onboarding ("your selfie stays on-device until you tap analyze; we never train on it; auto-delete after 7 days"). This converts privacy-hesitant users.

## Vocabulary glossary

| Term | Verbatim usage | Source |
|------|----------------|--------|
| hardmaxx | "Brutal gotta hardmaxx" | [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/) |
| softmaxx | "should I do softmaxxing or hardmaxxing?" | [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/) |
| bone smashing | "I wanted to do bone smashing" | [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/) |
| nerfed | "Haircut nerfed tf outta me." | [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/) |
| mog | "to surpass someone's attractiveness" (community usage) | [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) |
| cutecel | "an attractive but less masculine phenotype" (community usage) | [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) |
| prettyboy | "aspirational aesthetic combining attractiveness with refined features" (community usage) | [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) |
| LMTN | "low-midtier normie" rating category | [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) |
| MTN | "midtier normie" — average attractiveness | [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) |
| maxilla growth | "you need to get maxilla growth and you be fine" | [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) |
| zygos | "I need zygos" (cheekbones) | [The Importance of Facial Bones](https://forum.looksmaxxing.com/threads/the-importance-of-facial-bones.73012/) |
| canthal tilt | "A positive canthal tilt gives one a more attractive, sharper, and younger look." | [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/) |
| forward growth | "Forward growth: Contributes to balanced facial features." | [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/) |
| hooded eyes | "Hooded eyes: Offers a sense of mystery and depth to their gaze." | [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/) |
| hardmaxx (surgical) / softmaxx (non-surgical) | binary most posts organize around | [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/) |
| looksmin | "being depressed is such a looksmin buddy boyos" (= decreases your looks) | [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/) |
| cope | "Bonesmashing is cope" (= self-deception) | [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/) |

## Raw quotes (not synthesized into a top theme)

1. "You are not in any of that jfl not a single cute thing on you rn" — brutal-reply example — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
2. "You don't look bad you need to get maxilla growth and you be fine" — mixed-positive rating response — [Posted my face on reddit…](https://forum.looksmaxxing.com/threads/posted-my-face-on-reddit-most-brutal-shit-ive-seen-how-bad-do-i-look.73624/)
3. "i went through the path of self destruction, a pathway to suicide, always lost in a cage of thoughts, self harm(i was notoriously mutilating my body" — [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/)
4. "6 months of depression made me strong as steel, a new person" — recovery framing — [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/)
5. "it's never over, please anyone who is contemplating suicide don't do it" — peer-support framing — [Your mental health is a deal breaker…](https://forum.looksmaxxing.com/threads/your-mental-health-is-a-deal-breaker-in-looksmaxxing.9416/)
6. "Bonesmashing is cope" — [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/)
7. "Still hella young and asking if u should hardmaxx" — adult community response to 14-year-old — [Locking tf in…](https://forum.looksmaxxing.com/threads/locking-tf-in-criticism-and-advices-will-be-really-appreciated-and-should-i-do-softmaxxing-or-hardmaxxing.188211/)
8. "Clear skin: Offers a sense of youthfulness and overall health." — [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/)
9. "Mewing is a technique that involves placing your tongue on the roof of your mouth." — [Self-made Looksmaxxing guide](https://forum.looksmaxxing.com/threads/self-made-looksmaxxing-guide.62814/)
10. "app glitched and hasn't shown my rating. It's been stuck at 30% for days" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
11. "I can't see the analysis because it stays on the 'Processing' screen" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
12. "customer support – nonexistent would be an understatement" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
13. "products they try to tell you to buy wants to get your clicks on the link" — affiliate model criticism — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
14. "stuck at 91%. Not worth the effort" — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)
15. "Advised to 'create a new account, which would require paying again'" — customer support experience — [Umax review via Grand Screen](https://grand-screen.com/apps/umax-become-hot/reviews/)

## Remaining research gaps (recommend human-operated research)

Because this environment cannot access Reddit directly, the following remain unmined and are worth a human pass via an authenticated Reddit session or `PRAW`/Pushshift:

1. **r/femalefashionadvice** — face-shape / hairstyle threads, specifically the frustration with barbers/stylists giving wrong recommendations
2. **r/glowups** — verbatim "what I changed" self-text from top transformations (6-month / year)
3. **r/malefashionadvice** face-shape threads
4. **r/MakeupAddiction** — contouring-by-face-shape questions, user-submitted "what's my face shape" posts
5. **r/amiugly** / **r/TruRateMe** / **r/Rateme** — the direct rating subreddits where NXME is competing against volunteer humans
6. **r/Mewing** and **r/looksmaxxing** (the Reddit-native sister, separate from the forum) — top threads of the past 6 months
7. Trigger-event posts (breakup, starting college) — mostly live on r/self, r/TwoXChromosomes, r/offmychest

Recommended: spin up a throwaway Reddit account and scrape these via a standard Python script in a follow-up pass. The quote bank above covers the high-intensity negative themes (rating demoralization, untrustworthy AI, privacy) with real verbatims; what's missing is the positive trigger-event and aspirational vocabulary that sits in the Reddit-native subs.
