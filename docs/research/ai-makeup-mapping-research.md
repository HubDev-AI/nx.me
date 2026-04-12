# AI Makeup Mapping — Pre-Brainstorm Research

**Status**: Research dump (pre-brainstorm). Not a spec.
**Goal**: Collect models, settings, competitor intel, and data requirements so the brainstorm starts from facts.
**Date**: 2026-04-12
**Author**: /autoresearch:autoresearch (10 iterations)

---

## Working Definition

"AI Makeup Mapping" (as distinct from the existing NXME glow-up) is narrower and more controllable: the user picks or uploads a **reference look** (or named preset: *soft glam, clean girl, editorial smoky eye*) and the system applies **only makeup** to their selfie — lips, eyes, cheeks, brows, foundation — while keeping hair, identity, pose, background, and skin texture **unchanged**.

Compared to NXME's current `glowup_editorial` prompt (which allows hair + wardrobe + lighting changes), mapping is a surgical subset.

Core axes:

1. **Input**: selfie only vs. selfie + reference image vs. selfie + named preset vs. selfie + per-region palette (lip hex, eye hex, blush hex).
2. **Scope**: region-controlled (only lips) vs. full-face look.
3. **Identity preservation budget**: tighter than glow-up — skin texture must survive.
4. **Delivery mode**: static photo edit (v1) vs. live AR try-on (v2+).

---

## Iteration 1 — Scope & Competitor Landscape

### Market sizing

- Virtual makeup try-on market: **$1.11B (2024) → $1.86B (2032)**, CAGR **7.8%**. Broader AR beauty at CAGR **19.9%**.
- 60%+ of beauty shoppers use virtual try-on pre-purchase; up to **40% return reduction** and **90% conversion lift** when deployed by retailers.
- Only **15% of retailers** have deployed AR → first-mover opportunity still open.
- APAC = ~40% of the picture-beautification market (Meitu / YouCam dominate).

### Top players (2026)

| Rank | Player | Ownership | Market share / signal | Strength |
|------|--------|-----------|----------------------|----------|
| 1 | **Perfect Corp / YouCam Makeup** | Perfect Corp (public, HKEX) | 25.2% share, **1.1B downloads**, 800+ brand partners | AI shade matching (96/100), Face Analyzer detects 70+ features, B2B SDK |
| 2 | **ModiFace** | **L'Oréal** (acquired 2018) | #1 shade consistency (97/100) | Lab-backed shade fidelity, real-time AR tracking, live-stream integration (2025 engine refresh) |
| 3 | **Perfect365** | ArcSoft-originated, now standalone | Large consumer mindshare | Consumer polish, influencer collabs, extensive filter library |
| 4 | **Meitu** | Meitu Inc. (public, HKEX) | Dominant in APAC (BeautyCam, MeituPic, Wink) | Asian-beauty-optimized, AIGC-forward |
| 5 | **Banuba / Revieve / GlamAR** | Independent B2B | Emerging | White-label SDKs for retailers |

### Implication for NXME

- We are **not** competing with Perfect Corp on shade fidelity (they have lab data we don't).
- Our wedge is **editorial/creative makeup looks** (TikTok-viral, mood-board-driven) rather than *"match this exact lipstick SKU"*.
- We should treat mapping as a **creativity tool**, not a shopping tool.
- Mobile-first, photo-based (not live-AR) is fine for v1 — AR is table stakes for brand-driven try-on, not for content creation.

### Sources

- [Virtual Makeup Try-On Market Outlook 2026-2032 — IntelMarketResearch](https://www.intelmarketresearch.com/virtual-makeup-try-on-market-22056)
- [AR & AI Virtual Makeup Try-On: 20 Platforms Accuracy Comparison 2026 — BMFitt](https://www.bmfitt.com/reports/ar-ai-virtual-makeup-try-on/)
- [Top 30 Best AI Apps for Makeup in 2025 — BornByAI](https://bornbyai.com/ai-apps-for-makeup/)
- [AI Makeup Market — Future Market Insights](https://www.futuremarketinsights.com/reports/ai-makeup-market)
- [Picture Beautification App Market — Verified Market Reports](https://www.verifiedmarketreports.com/product/picture-beautification-app-market/)

---

## Iteration 2 — Commercial Tech Stacks (What The Leaders Actually Run)

### Perfect Corp / YouCam — canonical pipeline

Proprietary **AgileFace®** tech stack. The reference architecture all competitors mimic:

1. **Capture & pre-process** — camera frame → resize → color correction.
2. **Face detection** (low-res CNN for speed) + refined **landmark tracking** (200+ points).
3. **3D face mesh** generation → pose / blendshapes per frame.
4. **Semantic segmentation** — per-pixel masks for lips, skin, hair, brows.
5. **Shader-based rendering** — lipstick gloss reacts to dynamic light/shadow with head tilts; foundation blends against extracted skin tone.
6. **On-device compute** — no images leave the phone (privacy / latency).

### What this means technically

- Not a single generative model — a **classical CV + GPU shader pipeline** with an ML frontend.
- Real-time AR is achievable because the heavy lifting is **masking + color blending**, not full image generation.
- Accuracy claim (96–97/100 shade consistency) comes from *lab-measured* reference data + calibrated shader params, which we don't have.
- Same stack is reused for YouCam Video, AI Skin Diagnostic, and embedded in Google Search / YouTube / Snap try-ons.

### ModiFace (L'Oréal)

- World's first real-time AR beauty tracker for the web (WebGL-based).
- 2025 refresh: "AI-driven real-time makeup simulation engine" for live-stream shopping.
- Validated against L'Oréal cosmetic lab data → 97/100 shade consistency.
- Also white-labelled (Sephora Virtual Artist historically used ModiFace).

### Banuba / Revieve / GlamAR (B2B SaaS challengers)

- Offer Face AR SDKs for iOS/Android/Web (ARKit/ARCore + custom neural face tracker).
- Typical feature set: 60FPS face tracking, 3D mesh, per-region segmentation, shader effects.
- Business model: per-seat or per-MAU licenses for retailers.

### Implication for NXME

NXME's current stack is **cloud-based image generation** (fal.ai endpoints) — the opposite axis from the AR-SDK incumbents.

- **Don't try to match Perfect Corp's real-time AR** — wrong battle, wrong tech stack.
- Our strength is *generative quality + creative looks* the classical pipeline can't produce (e.g. "give me *Euphoria*-style glitter tears on my selfie" — classical shaders can't do that, diffusion can).
- The mapping feature should lean into **what only a generative model can do**: aesthetic-driven, reference-driven, concept-driven makeup — not pixel-accurate SKU matching.

### Sources

- [A look inside Perfect Corp's YouCam Makeup — Business of Business](https://www.businessofbusiness.com/articles/perfect-corp-youcam-makeup-app-beauty-tech-ar/)
- [Perfect Corp Virtual Makeup Filter SDK](https://www.perfectcorp.com/business/services/sdk)
- [8 Best Virtual Makeup SDKs Compared — DZone](https://dzone.com/articles/8-best-virtual-makeup-sdks-compared)
- [Perfect Corp AR makeover tech / YouCam Video — Auganix](https://www.auganix.org/augmented-reality-makeover-tech-provider-perfect-corp-launches-new-standalone-video-editing-app-youcam-video/)

---

## Iteration 3 — GAN-Based Makeup Transfer (Academic Line)

Reference-based makeup transfer has an ~8-year academic lineage before diffusion took over.

### Family tree

| Method | Year | Approach | Params | Strength | Weakness |
|--------|------|----------|--------|----------|----------|
| **BeautyGAN** | 2018 | Histogram matching + dual I/O GAN | 8.43M | Introduced the MT-Dataset + makeup loss — still the canonical baseline | Frontal faces only; transfers *color distribution* not details |
| **PSGAN** | 2020 | Attentive Makeup Morphing + pixel-wise alignment | 12.62M | Pose-robust; handles misalignment | Ignores fine texture, tends to shift background color |
| **LADN** | 2019 | Local adversarial disentangling | — | Extreme/complex looks | Artifacts, low fidelity on standard looks |
| **SCGAN** | 2021 | Component-wise style codes | 15.30M | Per-region (lips/eyes/cheeks) control | Oversmooths details |
| **CPM (Color-Pattern Makeup)** | 2021 | UV-space texture transfer | 9.24M | Handles patterns (glitter, graphics) | No forehead; "pasting" artifacts on face contour |
| **SSAT** | 2022 | Symmetric semantic-aware transformer | 10.48M | Joint transfer + **removal** — relevant for reference-free undo | Preserves content but low makeup fidelity for complex looks |
| **FAT** | 2022 | Transformer-based semantic interaction | — | Semantic alignment | Complex training |
| **EleGANt** | 2022 | Shifted-window attention, localized editing | — | Per-region editing support | Low fidelity on complex makeup |
| **BeautyREC** | 2023 | Component-specific makeup transfer | — | Faster than prior SOTA, high accuracy | Limited release / weights |
| **CSD-MT** | CVPR 2024 | Content-Style Decoupling, **unsupervised** (no pseudo-pairs) | — | No need for paired supervision; better than all GAN priors | Still GAN-era quality ceiling |

### Core limitation (shared across GANs)

> "PSGAN, SCGAN, EleGANt, SSAT preserve source content well but have **low fidelity for reference makeup, especially complex styles**, and tend to modify background color."

GANs are bottlenecked by **pseudo-paired training data** — histogram-matching or geometric-warping fakes, which cap what the model can learn about fine makeup detail.

### Datasets they all use

- **MT-Dataset** (BeautyGAN, 2018) — ~1,000 non-makeup + ~2,000 with-makeup female faces. The canonical benchmark.
- **Makeup-Wild (M-Wild)** (PSGAN) — in-the-wild poses, harder.
- **LADN** — extreme/pattern looks (gold leaf, face art, festival makeup).

### Implication for NXME

- GAN-based methods are **research-grade open-source**. Not productionized for mobile at our quality bar.
- Inference costs are low (8–15M params ≈ runs on a phone GPU), but **quality ceiling is the issue** — they can't deliver what Instagram-caliber users expect in 2026.
- **Do not build on GANs as our primary stack.** Fine as a *fallback* or for on-device preview, but diffusion is where quality lives now.
- SSAT's bidirectional *transfer + removal* is interesting — we'd want a "remove my makeup" button to let users preview a clean base before applying a new look.

### Sources

- [awesome-makeup-transfer — thaoshibe GitHub](https://github.com/thaoshibe/awesome-makeup-transfer)
- [BeautyREC: Component-Specific Makeup Transfer — CVPR 2023](https://openaccess.thecvf.com/content/CVPR2023W/NTIRE/papers/Yan_BeautyREC_Robust_Efficient_and_Component-Specific_Makeup_Transfer_CVPRW_2023_paper.pdf)
- [CSD-MT: Content-Style Decoupling Unsupervised Makeup Transfer — arXiv 2405.17240](https://arxiv.org/html/2405.17240)
- [SSAT: Symmetric Semantic-Aware Transformer for Makeup Transfer and Removal](https://www.researchgate.net/publication/361777958_SSAT_A_Symmetric_Semantic-Aware_Transformer_Network_for_Makeup_Transfer_and_Removal)
- [Canonical Makeup Transfer — BMVC 2025](https://bmva-archive.org.uk/bmvc/2025/assets/papers/Paper_664/paper.pdf)

---

## Iteration 4 — Diffusion-Based Makeup (The Current SOTA Line)

Diffusion overtook GANs for makeup transfer in 2024. The paper landscape is moving fast — two major 2025 releases (**FLUX-Makeup**, **DreamMakeup**) are the most relevant to NXME's stack.

### Current SOTA methods

| Method | Year / Venue | Base | Training | Key trick | Relevance to NXME |
|--------|--------------|------|----------|-----------|-------------------|
| **Stable-Makeup** | SIGGRAPH 2025 (arXiv 2024) | SD 1.5 | Fine-tune | Detail-Preserving encoder + **dual ControlNets** (content + structure via dense colored facial-key-point lines) + CLIP multi-layer features | Open-source, SD-based |
| **SHMT** | NeurIPS 2024 | Latent diffusion | Self-supervised | Laplacian-pyramid texture decomposition + Iterative Dual Alignment (IDA) | Open-source, avoids pseudo-pair problem |
| **MakeupDiffuse** | 2024 | Pretrained LDM | Teacher-student | Double image controller (identity + style); uses prior GAN as teacher | — |
| **FLUX-Makeup** | Aug 2025, arXiv 2508.05069 | **FLUX-Kontext** (DiT) | Fine-tune with RefLoRAInjector | **No auxiliary face-control modules** — LoRA injection balances identity vs. fidelity | 🔥 **HIGHLY RELEVANT** — NXME already runs `kontext` on fal.ai. Open-source at 360CVGroup/FLUX-Makeup. |
| **DreamMakeup** | Oct 2025, arXiv 2510.10918 | SD 1.5 + SD 3.0 | **Training-free** | Early-stopped DDIM inversion + latent-space interpolation (1–2 early steps); accepts reference image **OR** RGB hex **OR** text | 🔥 Relevant — training-free means usable without dataset collection |

### Key takeaways

- **Identity preservation is the bottleneck** across all diffusion methods. Stable-Makeup has known poor identity preservation; SHMT has inaccurate color; FLUX-Makeup/DreamMakeup explicitly designed to fix this.
- **FLUX-Kontext is the strongest base** for our use case because it's production-accessible on fal.ai (we already use it) and FLUX-Makeup demonstrates a working LoRA-injection pattern on top.
- **Training-free path (DreamMakeup)** = zero dataset collection cost. Plug into SD 1.5 or SD 3.0 via early-stopped DDIM inversion. Cheaper R&D path.
- **Paired data remains the bottleneck** for any fine-tuning path. Every fine-tuned method fights pseudo-pair quality.

### Standard diffusion eval metrics (adopted)

- **CLIP-I** — cosine sim between CLIP features of reference and generated → measures makeup transfer fidelity.
- **SSIM** — structural similarity between source and generated → measures identity preservation.
- **L2-M** — L2 on background regions after face parsing → measures background consistency.

### Implication for NXME

- **Two viable R&D paths** — both build on the flux models we already integrate.
  1. **Training-free** (à la DreamMakeup): implement early-stopped DDIM inversion + latent interpolation on top of an existing fal.ai flux endpoint. Zero new training. Ship-ready with prompt/setting work.
  2. **LoRA-injection** (à la FLUX-Makeup): train a small RefLoRAInjector on curated paired data, serve via fal-ai/flux-lora or a custom endpoint. Higher quality ceiling, needs dataset + training budget.
- Anything pre-2024 (GANs) is a dead end for us.

### Sources

- [Stable-Makeup project page](https://xiaojiu-z.github.io/Stable-Makeup.github.io/)
- [Stable-Makeup arXiv 2403.07764](https://arxiv.org/abs/2403.07764) · [GitHub](https://github.com/Xiaojiu-z/Stable-Makeup)
- [SHMT arXiv 2412.11058](https://arxiv.org/html/2412.11058v1)
- [FLUX-Makeup arXiv 2508.05069](https://arxiv.org/abs/2508.05069) · [GitHub 360CVGroup/FLUX-Makeup](https://github.com/360CVGroup/FLUX-Makeup)
- [DreamMakeup arXiv 2510.10918](https://arxiv.org/abs/2510.10918)
- [ControlNet primer](https://arxiv.org/abs/2302.05543)
- [IP-Adapter FaceID Plus v2](https://huggingface.co/h94/IP-Adapter-FaceID)

---

## Iteration 5 — Face Landmarking & Parsing (Masks for Precision)

"Makeup mapping" implies per-region control — you want to swap **only** the lip color, **only** the eyeshadow pattern. That requires knowing which pixels belong to each region. Two layers matter:

### Layer A — Landmarking (point-based)

| Solution | Points | Runtime | Accuracy | Mobile | Notes |
|----------|--------|---------|----------|--------|-------|
| **MediaPipe Face Mesh** | 468 3D + optional **attention mesh** refining lips/eyes/irises | Real-time mobile | **99.3%** vs dlib/MTCNN on benchmark | ✅ iOS/Android/Web | Free, Apache-2.0, `refine_landmarks=True` gives lip/eye refinement. NXME already has `app/face_analysis/landmark_extractor.py` |
| **dlib 68-point** | 68 | CPU-fast | Lower (pre-deep-learning era) | ✅ | Legacy |
| **MTCNN** | 5 | Fast | Detection only | ✅ | — |
| **Face++ / commercial APIs** | 106–150 | Cloud | High | API-only | Cost per call |

### Layer B — Parsing (pixel masks)

| Model | Classes | Trained on | Strength | Weakness |
|-------|---------|-----------|----------|----------|
| **BiSeNet face-parsing.PyTorch** | 19 (skin, lips upper/lower, eyes, brows, hair, nose, ...) | CelebAMask-HQ (30k @ 512×512) | Real-time, lightweight, MIT-licensed, widely used | Lower accuracy than SOTA on fine-grained regions |
| **EasyPortrait** | 9 | 40k images | Portrait/segmentation focus | Larger model |
| **SegFormer-face / DeepLabv3+** | configurable | various | Higher accuracy | Heavier, not real-time |

### The right pattern (hybrid)

Most AR/makeup pipelines use both:

1. Landmarks → **tracking, alignment, anchoring** (fast).
2. Parsing → **precise per-pixel masks** for where to paint (slower but necessary for pixel-accurate color blending).

For diffusion-based makeup, masks feed two things:
- **Input conditioning** — ControlNet takes the parsing map as spatial constraint.
- **Output compositing** — paste generated makeup back onto original *only* in the masked regions (preserves skin texture and identity in unmasked regions).

### Implication for NXME

- We **already use MediaPipe-style landmark extraction** (`app/face_analysis/landmark_extractor.py`). That's layer A covered.
- We do **not** have a parsing model in the stack. For mapping we'll need one — BiSeNet is the pragmatic default (CelebAMask-HQ, 19 classes including lower-lip/upper-lip split, MIT-licensed, runs on a small model).
- For per-region controls ("change only lips"), parsing is non-negotiable. Prompt-only control on flux does not give pixel-level isolation.

### Sources

- [MediaPipe Face Mesh docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/face_mesh.md)
- [face-parsing.PyTorch (BiSeNet + CelebAMask-HQ)](https://github.com/zllrunning/face-parsing.PyTorch)
- [CelebAMask-HQ dataset](https://github.com/switchablenorms/CelebAMask-HQ)
- [EasyPortrait face-parsing dataset arXiv 2304.13509](https://arxiv.org/html/2304.13509v3)
- [ONNX-ready face-parsing (yakhyo)](https://github.com/yakhyo/face-parsing)

---

## Iteration 6 — Commercial APIs Available Today

### Key finding

**No managed "makeup transfer" endpoint exists** on fal.ai or Replicate as of 2026-04. This is a real gap (and a real opportunity for whoever wraps one).

### What we can compose on fal.ai (our current vendor)

| Endpoint | Cost | Capability | Fit for mapping |
|----------|------|-----------|-----------------|
| `fal-ai/flux/kontext` (already in our adapter) | low–mid | Iterative edits that preserve identity naturally | ✅ Best generic fit. Can prompt makeup changes directly. |
| `fal-ai/flux-general/image-to-image` | mid | SDXL-style img2img **with LoRA + ControlNet + IP-Adapter** slots | ✅ Plug in a makeup LoRA (or FLUX-Makeup's RefLoRA) here. |
| `fal-ai/ip-adapter-face-id` | low | Zero-shot identity preservation from a face image | ⚠️ Designed for face swap / identity cloning, not reference-makeup transfer. Identity side only. |
| `fal-ai/flux-pulid` (already in our adapter) | mid | PuLID identity-preserving T2I | ⚠️ Strong identity lock, weaker on edit specificity. |
| `fal-ai/nano-banana-pro` (already in our adapter) | high ($0.15/img) | Gemini 3 Pro Image, semantic reasoning on edits | ✅ High quality, expensive. Good for hero/premium tier. |
| `fal-ai/flux-lora` | mid | Serve a custom fine-tuned LoRA on FLUX.1 | ✅ If we train our own makeup LoRA, this is where it runs. |

### Replicate

- No official BeautyGAN/PSGAN endpoint.
- Community-published model ports would run in the **$0.002–$0.015/image** range on T4/A100 GPUs billed per second.
- Not a competitive delivery path — higher latency and less ergonomic than fal for our stack.

### Self-host options

- **fal GPU fleet** — H100 from **$1.89/hr**; deploy custom model as a fal app. Viable for a fine-tuned makeup model if we go that route.
- **Replicate Cog** — package BeautyGAN / SHMT / Stable-Makeup and ship. Same cost structure.
- **Direct GPU hosting** (Runpod, Modal) — cheaper per-hour, more ops overhead.

### NXME cost context

Our code already defines cost ceilings:

- `IMAGE_GEN_COST_CEILING_USD=0.06` — per-generation hard cap.
- `CREDIT_COST_ALERT_USD=0.05` — alerting threshold.

Any makeup-mapping endpoint we pick needs to fit **under $0.06/image** to stay within existing economics. That rules out nano-banana-pro for the default mapping flow (can be premium-tier only); flux-kontext/flux-general/flux-lora all fit.

### Implication for NXME

- **v1 path**: compose flux-kontext + prompt engineering + optional IP-Adapter-FaceID for identity — all on fal.ai, zero new infra, within budget.
- **v2 path**: train a makeup LoRA (FLUX-Makeup-style) and serve via `fal-ai/flux-lora`. Higher quality ceiling, requires dataset work.
- **v3 path**: train a DiT-native makeup model, host on fal custom app. Highest ceiling, highest investment.

### Sources

- [fal.ai model explorer](https://fal.ai/explore)
- [fal-ai/ip-adapter-face-id API](https://fal.ai/models/fal-ai/ip-adapter-face-id/api)
- [fal-ai/flux-general/image-to-image API](https://fal.ai/models/fal-ai/flux-general/image-to-image/api)
- [fal.ai pricing docs](https://fal.ai/docs/platform-apis/v1/models/pricing)
- [all fal.ai models & prices — community gist](https://gist.github.com/azer/6e8ffa228cb5d6f5807cd4d895b191a4)
- [Replicate pricing](https://replicate.com/pricing)

---

## Iteration 7 — Datasets & Training Data Requirements

### Public datasets (canonical)

| Dataset | Size | Content | Resolution | License | Source |
|---------|------|---------|-----------|---------|--------|
| **MT-Dataset** (BeautyGAN 2018) | 3,834 images (1,115 non-makeup + 2,719 makeup) female faces | Retro, Japanese, Korean, light/heavy | 361×361 | Research-use, via Google Drive — no explicit LICENSE file. Check before commercial use. | BeautyGAN GitHub |
| **Makeup-Wild (M-Wild)** (PSGAN 2020) | 772 images | In-the-wild poses | varies | Research | PSGAN OneDrive |
| **LADN** (2019) | 635 images (333 non-makeup, 302 makeup + 115 artistic) | Extreme/artistic looks | high | Research | LADN GitHub |
| **LADN-Syn** | 120K synthetic warp-and-paste pairs | Weak realism | — | Research | LADN |
| **CPM-Real** (VinAI 2021) | 3,895 in-the-wild | Wide styles, ages, poses | multi | Research | VinAIResearch/CPM |
| **CPM-Synt-1** | 5,555 synthetic | Transferred-pattern training | 256×256 | Research | CPM |
| **CPM-Synt-2** | 1,625 triplets (source/ref/GT) + 1,115 same-color triplets | Ground-truth experiments | 256×768 | Research | CPM |
| **Stickers** | unknown | Face art / patterns | multi | Research | CPM |
| **MT-Text** | extension | Text→makeup multi-modal | — | Research | Recent |
| **FFHQ-Makeup** (arXiv 2508.03241, 2025) | paired synthetic | Facial consistency across styles | FFHQ-native | Research | Recent |

### Face-parsing data for our mask pipeline

- **CelebAMask-HQ** — 30,000 images, 512×512, **19-class pixel masks** including `lower_lip`, `upper_lip`, `l_eye`, `r_eye`, `l_brow`, `r_brow`, `nose`, `skin`, `hair`, `hat`, etc. → the dataset backing BiSeNet face-parsing.

### What a custom training run would require

1. **Pairs of {clean face, made-up face}** — ideal but impossible to collect at scale without stage/lab setup.
2. **Pseudo-pairs** via warp-paste or histogram matching — the path GANs take. Supervision quality is limited (this is the known failure mode).
3. **Self-supervised decomposition** (SHMT) or **training-free inversion** (DreamMakeup) — avoid the paired-data problem entirely.
4. **Licensing** — public sets are research-licensed. **Do not train a commercial model on them without permission.** Would need to collect/license our own or commission.

### Realistic options for NXME

| Path | Data needed | Cost | Time |
|------|------------|------|------|
| **Training-free (DreamMakeup-style)** | None | $0 | days |
| **LoRA fine-tune** (FLUX-Makeup-style) | ~5–10k paired / pseudo-paired examples | GPU ~$200–$1,000; dataset collection / licensing harder | 2–4 weeks |
| **Full model train** | 100k+ examples + lab-grade pairs | $10k+ and a legal review | 2–3 months |
| **Buy Perfect Corp SDK license** | None | Enterprise pricing (undisclosed, typically 5–6 figures/yr) | Contract + integration |

### Implication for NXME

- Do **not** spin up custom training until we validate v1 (training-free or prompt-only) can't deliver.
- If we need fine-tuning, **license-check everything** before touching MT-Dataset / LADN / CPM for commercial training.
- FFHQ-Makeup (2025) is the freshest set — worth tracking for license terms before using.

### Sources

- [CPM / "Lipstick ain't enough" — VinAIResearch](https://github.com/VinAIResearch/CPM)
- [Makeup transfer: A review (He 2023) — IET Computer Vision](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/cvi2.12142)
- [FFHQ-Makeup arXiv 2508.03241](https://arxiv.org/html/2508.03241)
- [awesome-makeup-transfer dataset index](https://github.com/thaoshibe/awesome-makeup-transfer)
- [CelebAMask-HQ](https://github.com/switchablenorms/CelebAMask-HQ)

---

## Iteration 8 — Evaluation Metrics & Identity Preservation

### The canonical quartet (used in every paper)

| Metric | Measures | Range / direction | How it's computed |
|--------|----------|-------------------|-------------------|
| **ArcFace IDS** (identity similarity) | Did the person stay the same? | 0–1, higher better | cosine similarity between ArcFace 512-d embeddings of source vs. output; loss = `1 − cos(φ(src), φ(out))` |
| **FID** | Overall realism vs. a reference distribution | lower better | Fréchet distance between InceptionV3 features of generated set vs. FFHQ/MT target distribution (needs large N) |
| **LPIPS** (or face-region **fLPIPS**) | Perceptual similarity | lower better | AlexNet-feature L2; fLPIPS computed only over face-parsing masks |
| **SSIM / PSNR** | Pixel fidelity vs. source | higher better | structural similarity — used for identity/structure preservation |

Diffusion-specific additions (FLUX-Makeup):

- **CLIP-I** — CLIP-encoded cosine sim between **reference** and **generated** → *makeup* fidelity (did the output capture the reference look?).
- **L2-M** — L2 over background regions (via face-parsing mask) → background preservation.

### User study patterns (always run alongside metrics)

Human ratings capture what metrics miss. Standard four-axis rubric:

1. **Makeup quality** — does it look like real applied makeup?
2. **Reference similarity** — does it match the reference look?
3. **Identity preservation** — is it clearly the same person?
4. **Naturalness** — no uncanny-valley / AI artifacts.

Pairwise A/B or Likert 1–5 per axis. Typical n=30–100 raters.

### What NXME already has

Good news: **most of this is already wired up**.

| Piece | File | Status |
|-------|------|--------|
| ArcFace identity comparison | `app/generation/models.py` → `IdentityCheckResult` | ✅ Built |
| Identity preservation failure path | `app/generation/models.py` → `FAILURE_IDENTITY` | ✅ Built |
| Multi-candidate scoring (ArcFace + "wow") | `app/generation/models.py` → `CandidateResult` | ✅ Built |
| Cost estimation per model | `FalAiAdapter._estimate_cost` | ✅ Built |

We can reuse the existing `arcface_score` pipeline to reject identity-broken mapping outputs without writing anything new. We'd want to **add** CLIP-I (for reference similarity) and potentially L2-M (for background consistency) if we add reference-image-driven mapping.

### Practical thresholds (from literature + Protégé baseline)

- **ArcFace IDS ≥ 0.80** → same person, reliable.
- **0.65 ≤ IDS < 0.80** → grey zone, probably same person but makeup may have pushed it.
- **IDS < 0.65** → treat as identity broken; reject.
- **FID < 30** considered competitive on MT/FFHQ.

(The existing NXME FAILURE_IDENTITY threshold should be checked against what's already configured.)

### Sources

- [Identity-preservation loss in generative models — EmergentMind](https://www.emergentmind.com/topics/identity-preservation-loss)
- [Face Similarity Evaluation in Image and Video Generation — Zenn](https://zenn.dev/taku_sid/articles/20250511_face_sim_metric)
- [Protégé Makeup GAN — arXiv 2412.20381](https://arxiv.org/html/2412.20381v1)
- [TinyBeauty (Data Amplify Learning) — arXiv 2403.15033](https://arxiv.org/html/2403.15033)
- [AuraFace open-source face recognition — HF blog](https://huggingface.co/blog/isidentical/auraface)
- [CLIP2Protect makeup-based adversarial — CVPR 2023](https://openaccess.thecvf.com/content/CVPR2023/papers/Shamshad_CLIP2Protect_Protecting_Facial_Privacy_Using_Text-Guided_Makeup_via_Adversarial_Latent_CVPR_2023_paper.pdf)

---

## Iteration 9 — Settings, Parameters & Prompt Strategies

### FLUX-Makeup paper's recommended settings (canonical starting point)

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Sampling steps** | **28** | Matches our FLUX.2 range (we currently use 30–40). |
| **Guidance scale** | **2.5** | **Lower than our current glow-up defaults (3.5–4.0)** — makeup transfer needs lighter guidance to avoid over-styling. |
| Training text prompt | Fixed to `"Makeup."` | They don't use rich text prompts; the LoRA carries the signal. |
| LoRA rank (RefLoRAInjector) | 256 | For custom training path only. |
| Reference preprocessing | Face-parse out non-face pixels from reference | Critical — otherwise background leaks. |
| Base model | FLUX.1 Kontext [dev] or [pro] | What we already use. |

### FLUX.1 Kontext prompting rules (Black Forest Labs official)

- **Use "change" or "apply", never "transform"** — "transform" is a magic word that signals full-image change.
- **Always specify what should stay the same**, not just what changes: "... while maintaining the same facial features, hairstyle, expression, skin texture, pose, lighting, and background."
- **Short, face-region-scoped prompts**. Avoid global style cues.
- **Reference the subject specifically** ("the woman with short black hair") rather than "her".
- **Iterate from the original, not from the previous edit** — reduces compounding drift.
- **Raise guidance** to preserve base composition; **lower guidance** for stronger edits within the face.

### Candidate v1 prompt template for NXME

```
Apply the makeup style from the reference to {identity_phrase}'s face —
including lipstick color, eyeshadow, blush, and eyeliner — while preserving
{identity_phrase}'s exact facial features, identity, skin texture, skin tone,
face shape, hairstyle, expression, pose, lighting, and background.
Only modify the makeup; keep everything else identical.
```

With `{identity_phrase}` pulled from the existing `_IDENTITY_PHRASES` rotation in `prompt_builder.py`.

### NXME's existing parameter surface (reusable)

From `app/generation/models.py::GenerationOptions` — all the knobs we need already exist:

```python
guidance_scale: float = 4.0        # lower to 2.5 for mapping
num_inference_steps: int = 35       # lower to 28 for mapping
strength: float | None = None       # 0.55 is the flux-dev default, push to ~0.4 for less change
ip_adapter_scale: float | None      # for identity lock on top of edit
id_weight: float = 0.95             # PuLID-specific identity strength
controlnet_conditioning_scale       # for ControlNet-based face-structure lock
```

### Negative prompt anchors (from NXME's existing memory)

Our stored prompt-tuning rules say:

> Prompt anti-AI anchors that work: "Shot on iPhone", "not retouched or filtered", "not an AI render", "candid feel". Negative prompt: "CGI", "uncanny valley", "overprocessed", "glossy skin".

Apply these to mapping too, plus makeup-specific negatives:

- Negative: "plastic skin", "cakey foundation", "airbrushed", "smoothed pores", "different person", "CGI", "overprocessed".

### Safe parameter ranges by model (from NXME's memory + FLUX-Makeup)

| Model | guidance_scale | steps | strength | Notes |
|-------|---------------|-------|----------|-------|
| `flux/kontext` (mapping) | **2.5** | **28** | n/a | Per FLUX-Makeup paper |
| `flux-2/flex-edit` (mapping) | 3.5–4.0 | 30–40 | n/a | Current glow-up range |
| `flux-general/img2img` | 4.0 | 30 | 0.4 (was 0.55 for glow-up) | Lower strength = less facial change |
| `flux-pulid` | 3.5–4.2 | 28–30 | n/a | id_weight 0.75–0.88 (locked range — NEVER <0.70 or >0.90) |
| `nano-banana-pro` | n/a (semantic) | n/a | n/a | `thinking_level: "high"` for mapping quality |

### Implication for NXME

- v1 mapping should **reuse** the existing `GenerationOptions` struct — no new adapter code needed, just a new module/mode that configures parameters differently.
- Add a `mapping` mode to prompt_builder.py alongside `everyday`/`polished`/`editorial`.
- New prompt templates: `mapping_reference.txt` (reference-image-driven) and `mapping_preset.txt` (named-look-driven).
- The `strength` lever is our best tool for "makeup only, don't change face shape" — drop it to ~0.4 on img2img paths.

### Sources

- [FLUX-Makeup arXiv 2508.05069 — settings §4.1](https://arxiv.org/html/2508.05069v1)
- [Black Forest Labs — Kontext Image-to-Image Prompting Guide](https://docs.bfl.ai/guides/prompting_guide_kontext_i2i)
- [Flux Kontext Prompt Guide — FluxAI.pro](https://fluxai.pro/blog/flux-kontext-prompt-guide)
- [MimicPC Flux Kontext Prompt Guide](https://www.mimicpc.com/learn/flux-kontext-prompt-guide-how-to-edit-images)
- [FLUX Kontext Face Swap ComfyUI Workflow](https://www.runcomfy.com/comfyui-workflows/comfyui-flux-kontext-face-swap-workflow-photoreal-swaps-localized-refinement)

---

## Iteration 10 — Synthesis & Brainstorm-Ready Recommendations

### TL;DR (one paragraph)

NXME should frame **AI Makeup Mapping** as a *creative makeup generation* feature (editorial / viral / mood-driven looks) — **not** a shade-matching shopping tool. That wedge is open: Perfect Corp and ModiFace dominate the shade-accurate AR try-on battle with lab data we can't match, but nobody owns "Euphoria-glitter-tears from a selfie in 5 seconds." The right v1 stack is a **training-free recipe on FLUX Kontext** (the model we already run on fal.ai), augmented with BiSeNet face-parsing masks for per-region control and our existing ArcFace identity gate. Start with 28 steps / guidance 2.5 per the FLUX-Makeup paper, reuse our `GenerationOptions`, add a new prompt mode. If v1 hits a quality ceiling, the upgrade path is a makeup LoRA served via `fal-ai/flux-lora`. Everything stays under the $0.06/image ceiling.

### Three implementation paths (pick 1 for v1)

#### Path A — Prompt + Parameter Tuning (training-free)

**What**: New `mapping` mode in `prompt_builder.py`; new prompt templates; drop guidance to 2.5, steps to 28, strength to ~0.4 on flux-kontext. Add BiSeNet face-parsing for per-region masks. Accept either (a) a named preset (`soft_glam`, `clean_girl`, `editorial_smoky`), (b) a reference selfie, or (c) a hex palette.

- **Cost/time**: 1–2 weeks eng, no training, no data collection.
- **Cost/image**: ~same as existing glow-up (under $0.06 ceiling).
- **Quality ceiling**: bounded by FLUX-Kontext's base makeup understanding. Text-only looks will be good; complex reference-image fidelity will be medium.
- **Risks**: Prompt drift; reference-image fidelity limited without injecting reference features properly.
- **Good for**: Fast ship, fast learning, establishes the product shape before investing in ML.

#### Path B — Training-Free Inversion Recipe (DreamMakeup-style)

**What**: Implement early-stopped DDIM inversion + latent-space interpolation on top of a Stable Diffusion or FLUX endpoint. Accepts reference image, hex color, or text. Still no model training — but smarter sampling than Path A.

- **Cost/time**: 3–6 weeks eng, needs diffusion-level engineering.
- **Cost/image**: Higher than Path A (more inference steps and custom logic). May push against the $0.06 ceiling depending on deploy.
- **Quality ceiling**: Higher than Path A per the DreamMakeup paper (better identity preservation, cleaner artifact-free results).
- **Risks**: Not natively supported by fal.ai's stock endpoints — would need custom app deploy on fal GPU fleet (~$1.89/hr H100) or similar.
- **Good for**: v2 if Path A hits ceiling, or if we want to differentiate on quality.

#### Path C — Custom Makeup LoRA on FLUX (FLUX-Makeup-style)

**What**: Train RefLoRAInjector (rank 256, text prompt "Makeup.") on paired makeup data. Serve via `fal-ai/flux-lora`.

- **Cost/time**: 1–3 months including data collection/licensing.
- **Cost/image**: Similar to `flux-lora` baseline, fits under $0.06 ceiling.
- **Quality ceiling**: Highest of the three.
- **Risks**: Dataset licensing — MT/LADN/CPM are research-only. Need to curate/license commercial-safe data. Training-pipeline complexity. Maintenance burden.
- **Good for**: v3 or parallel track once we know product-market fit.

### Recommended sequencing

1. **Sprint 0** (~1 week) — build the mapping module scaffold: new prompt mode, parameter presets per model (`flux-kontext` at 28/2.5), reuse existing `GenerationOptions` + `IdentityCheckResult`.
2. **Sprint 1** (~1–2 weeks) — add BiSeNet face-parsing service for lips/eyes/cheeks masks. Pipe masks through to compositing step (paste generated output back onto source via mask, preserving unmasked skin texture).
3. **Sprint 2** (~1 week) — ship 4–6 named preset looks with curated prompt+settings combos. A/B against existing glow-up to validate product.
4. **Sprint 3+** — if reference-image path is required, layer IP-Adapter-FaceID on flux-general/img2img, or start Path C (LoRA training).

### Build-vs-buy

| Option | Verdict |
|--------|---------|
| License Perfect Corp SDK | ❌ Wrong battle. Their value is lab-calibrated shade matching for brand try-on — not our creative-makeup wedge. Expensive. |
| License ModiFace | ❌ Same as Perfect Corp. B2B only, beauty-brand focused. |
| Banuba/Revieve/GlamAR SDKs | ⚠️ Could accelerate AR/live try-on if that becomes a v2 direction; overkill for v1. |
| **Build on fal.ai with FLUX Kontext** | ✅ **This is the recommended v1 path.** |

### Key open questions (for brainstorm)

1. **Input modality priority** — reference selfie, named preset, hex palette, or text description? Which is the hero and which is a nice-to-have?
2. **Per-region control UX** — do users get "change only lips" sliders/toggles, or is it always whole-face? (Affects whether face-parsing ships in v1.)
3. **Removal capability** — do we ship a "remove my makeup" inverse mode? (SSAT architecture supports this bidirectionally; useful for preview.)
4. **Pricing/tier** — is makeup mapping standard, premium, or credits-gated? Nano-banana-pro could be a premium-tier upsell at $0.15/img.
5. **Identity threshold** — do we reuse the existing `FAILURE_IDENTITY` threshold or tighten it for mapping (since the "do not change face" contract is stricter than glow-up)?
6. **Live AR** — is real-time AR a v2+ consideration, or explicitly out of scope forever? Determines whether we ever need the Perfect-Corp-style classical pipeline.
7. **Dataset strategy** — do we quietly start collecting opt-in paired data now (from our own users) to fuel Path C later? Privacy/consent implications.
8. **Legal review** — any commercial use of MT/LADN/CPM training data is a legal risk. Confirm path forward before anyone downloads them.

### What we already have that accelerates this

- ✅ fal.ai integration with 8 models (kontext, flux-2, flux-pulid, flux-general, nano-banana variants, instantid).
- ✅ Identity phrase rotation + deterministic seeding in `prompt_builder.py`.
- ✅ ArcFace identity-check with `FAILURE_IDENTITY` handling.
- ✅ Multi-candidate scoring pipeline (`CandidateResult`).
- ✅ Cost ceilings defined (`IMAGE_GEN_COST_CEILING_USD=0.06`).
- ✅ Known good parameter ranges per model (stored in memory).
- ✅ Face landmark extractor (`app/face_analysis/landmark_extractor.py`).
- ✅ Modular transformation registry (`app/generation/modules/`) — mapping slots in here.

### What's missing and has to be built

- ❌ Face parsing (BiSeNet) — new service/module.
- ❌ Per-region mask compositing (paste back generated output onto source via lips/eyes masks).
- ❌ Reference-image handling for mapping (currently source image is the only image input).
- ❌ Named-look preset library (prompt + parameter bundles).
- ❌ "Remove makeup" inverse direction (optional, stretch).
- ❌ CLIP-I metric for measuring reference-similarity (optional, only if reference mode ships).

### Final one-liner recommendation for the brainstorm

> **Ship Path A (prompt + parameter tuning on FLUX Kontext, 28 steps / guidance 2.5) with 4–6 curated preset looks, BiSeNet masks for per-region control, and our existing ArcFace identity gate. If v1 hits a quality ceiling, upgrade to a custom FLUX-Makeup-style LoRA (Path C).**

---

## Research Complete — 10/10 iterations ✓

Total sources touched: ~45 web references + internal code inspection of NXME's generation pipeline, prompt builder, models, and fal.ai adapter. Research doc lives at `docs/research/ai-makeup-mapping-research.md`. Brainstorm can start from here.







