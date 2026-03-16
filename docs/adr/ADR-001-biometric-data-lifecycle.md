# ADR-001: Biometric Data Lifecycle

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Engineering, Legal
**Tags:** GDPR, biometrics, privacy, NFR-10, NFR-12, FR-5

---

## Context

NXME performs facial analysis on user-uploaded selfies. This analysis extracts biometric features including:
- Landmark vectors (facial geometry keypoints)
- Identity embeddings (ArcFace-style similarity vectors)
- Inferred attributes (face shape, symmetry score, proportions)

Biometric data is a **special category** under GDPR Article 9. Storing it requires explicit consent and carries heightened obligations including the right to erasure (Article 17). Any persistence of raw biometric vectors creates regulatory exposure across EU, Illinois BIPA, Texas CUBI, and other jurisdictions.

The core question: should NXME persist biometric embeddings to enable future features (identity similarity deduplication, style evolution tracking), or compute them ephemerally per request?

---

## Decision

**Landmark vectors and ArcFace embeddings are ephemeral — computed in-request, never persisted.**

The `analyses` table stores only **derived metadata** (face_shape TEXT, symmetry_score FLOAT, is_valid_face BOOLEAN, landmark_json JSONB). `landmark_json` stores the 2D landmark coordinates used for the UI overlay — these are geometric descriptors of the image, not biometric identifiers, and are stored alongside the image they describe. They are NOT re-usable for identity matching.

ArcFace embeddings (high-dimensional identity vectors) are:
1. Computed in the face analysis adapter during a generation request
2. Used immediately for the identity similarity check (`analyses.identity_similarity_threshold`)
3. Discarded after the check — never written to any persistent store

---

## Legal Basis (GDPR)

| Processing Activity | Legal Basis | Article |
|--------------------|-------------|---------|
| In-request embedding computation | Legitimate interests (fraud prevention, duplicate detection) | Art. 6(1)(f) |
| Storing landmark_json with uploaded image | Performance of contract (providing the glow-up service) | Art. 6(1)(b) |
| Face shape / symmetry metadata | Performance of contract | Art. 6(1)(b) |

Because biometric embeddings are never persisted, GDPR Article 9 (special category processing) is satisfied by ensuring no persistent biometric record exists. No explicit consent is required for ephemeral in-request computation under the legitimate interests basis for fraud prevention.

---

## Consent Model

1. **At registration:** Users consent to AI-based facial analysis as part of the service (terms of service consent, not Article 9 explicit consent — because we do not store biometric data).
2. **At upload:** A clear in-app disclosure states: "Your selfie is analyzed by AI. Facial geometry is used to generate your results. No biometric ID vectors are stored."
3. **Right to erasure (FR-5):** Deleting an account cascades to delete all images and analyses (ON DELETE CASCADE in schema). No separate biometric record exists to delete.
4. **Minors:** The `is_minor` flag prevents upload until a guardian consent step is completed (Story 2-1 AC).

---

## Identity Similarity Check

The `identity_similarity_threshold` stored per tier (in the `tiers` table) is used to reject near-identical submissions that could indicate duplicate accounts. The comparison is:

```
compute embedding(new_image) → compare cosine_similarity with embedding(recent_image_for_user)
                                ↑ recent image embedding computed fresh each time, not retrieved from store
```

If the threshold check must compare against historical submissions, the image itself (stored in Supabase Storage) is re-processed ephemerally. The embedding is never cached.

---

## Consequences

**Benefits:**
- No Article 9 special category processing — substantially lower regulatory burden
- Right to erasure satisfied trivially via cascade delete
- No biometric database to protect or breach

**Tradeoffs:**
- Style evolution / "Future You" features cannot use stored embeddings — must re-compute on demand from stored images
- Identity deduplication across different images requires re-computing embeddings, adding latency to that path
- Cannot implement long-term identity trend tracking without storing a derived (non-biometric) representation

**Future consideration:** If style evolution tracking requires persistent identity representations, a separate ADR must be written documenting the legal basis, explicit consent mechanism, and storage design before implementation.

---

## Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Persist ArcFace embeddings** | Enable style evolution, fast deduplication | Article 9 obligation, BIPA exposure, breach risk | Rejected |
| **Ephemeral computation (chosen)** | No Article 9, trivial erasure | Re-compute cost for deduplication | Accepted |
| **Pseudonymised embedding store** | Partial compliance improvement | Still special category under GDPR | Rejected |
