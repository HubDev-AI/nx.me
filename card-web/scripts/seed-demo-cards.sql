-- Seed demo cards for card-web design review.
-- Run: psql postgresql://postgres:postgres@127.0.0.1:54322/postgres -f card-web/scripts/seed-demo-cards.sql
--
-- Creates 12 users, each with an analysis, job, and post.
-- Image URLs point to card-web local dev server (localhost:3006/images/...).
-- Idempotent: skips users that already exist by username.

BEGIN;

-- Helper: base URL for local card-web images
\set img_base 'http://localhost:3006/images'

DO $$
DECLARE
  _uid UUID;
  _img_before UUID;
  _img_after UUID;
  _img_selfie UUID;
  _analysis_id UUID;
  _job_id UUID;
  _base TEXT := 'http://localhost:3006/images';
BEGIN

-- ────────────────────────────────────────────────────────────────
-- Helper procedure for inserting one complete demo card
-- ────────────────────────────────────────────────────────────────
-- We inline each user to keep the SQL portable (no dynamic SQL).

-- ── 1. sophia ──────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'sophia') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'sophia', 'Sophia Rivera', 'sophia@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status)
  VALUES (gen_random_uuid(), _uid, 'demo/sophia-selfie', 'selfie', 'cleared')
  RETURNING id INTO _img_selfie;

  INSERT INTO images (id, user_id, storage_key, image_type, status)
  VALUES (gen_random_uuid(), _uid, 'demo/sophia-before', 'generated_before', 'cleared')
  RETURNING id INTO _img_before;

  INSERT INTO images (id, user_id, storage_key, image_type, status)
  VALUES (gen_random_uuid(), _uid, 'demo/sophia-after', 'generated_after', 'cleared')
  RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'oval', 0.87,
    '[{"rank":1,"category":"Hairstyle","suggestion_text":"Try a textured mid-length cut with side-swept layers for a more dynamic silhouette that frames your face shape beautifully.","rationale":"Your oval face can handle asymmetry well."},
      {"rank":2,"category":"Color Palette","suggestion_text":"Deep jewel tones like burgundy, emerald, and sapphire would complement your complexion beautifully.","rationale":"Warm undertone pairs with rich colors."},
      {"rank":3,"category":"Accessories","suggestion_text":"A minimal gold pendant necklace adds just enough detail to elevate a plain outfit without looking overdone.","rationale":"Simple metallic accents match your warm tone."},
      {"rank":4,"category":"Clothing","suggestion_text":"A structured blazer over a simple crew-neck tee creates an effortlessly put-together look for any occasion.","rationale":"Adds formality without sacrificing comfort."},
      {"rank":5,"category":"Grooming","suggestion_text":"Shape your brows with a professional wax — well-groomed brows are the single highest-impact facial change.","rationale":"Brow shaping enhances facial symmetry."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-sophia', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW())
  RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-53.jpg', _base || '/after-53.jpg', 342, 47);

  RAISE NOTICE 'Created demo card: sophia';
END IF;

-- ── 2. marcus ──────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'marcus') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'marcus', 'Marcus Chen', 'marcus@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status)
  VALUES (gen_random_uuid(), _uid, 'demo/marcus-selfie', 'selfie', 'cleared')
  RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status)
  VALUES (gen_random_uuid(), _uid, 'demo/marcus-before', 'generated_before', 'cleared')
  RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status)
  VALUES (gen_random_uuid(), _uid, 'demo/marcus-after', 'generated_after', 'cleared')
  RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'square', 0.82,
    '[{"rank":1,"category":"Clothing","suggestion_text":"Swap the oversized tee for a well-fitted linen button-down in a warm earth tone — instant polish without trying too hard.","rationale":"Fitted silhouettes suit your frame."},
      {"rank":2,"category":"Hairstyle","suggestion_text":"A soft curtain fringe would complement your face shape — ask your stylist for a center-parted layered cut.","rationale":"Softens angular jawline."},
      {"rank":3,"category":"Fit","suggestion_text":"Your jeans are a size too large — get them tapered from the knee down for a cleaner line without sacrificing comfort.","rationale":"Proportion correction maximizes visual height."},
      {"rank":4,"category":"Footwear","suggestion_text":"White leather sneakers with a chunky sole would modernize your casual looks — keep them clean for maximum effect.","rationale":"Clean footwear anchors a casual outfit."},
      {"rank":5,"category":"Accessories","suggestion_text":"A quality leather watch strap in cognac or tan adds warmth and intention to any casual outfit.","rationale":"Leather tones tie earth palette together."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-marcus', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW())
  RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-1.jpg', _base || '/after-1.jpg', 189, 23);

  RAISE NOTICE 'Created demo card: marcus';
END IF;

-- ── 3. aisha ───────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'aisha') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'aisha', 'Aisha Patel', 'aisha@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/aisha-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/aisha-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/aisha-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'heart', 0.91,
    '[{"rank":1,"category":"Grooming","suggestion_text":"A consistent skincare routine with SPF 30+ daily and vitamin C serum will give you a noticeable glow within weeks.","rationale":"Protection and brightening for even skin tone."},
      {"rank":2,"category":"Color Palette","suggestion_text":"Your skin undertone is warm — build around terracotta, olive, mustard, and cream instead of cool blues and grays.","rationale":"Warm tones enhance natural radiance."},
      {"rank":3,"category":"Hairstyle","suggestion_text":"Consider a modern shag cut with face-framing pieces to add movement and dimension.","rationale":"Frames heart-shaped face beautifully."},
      {"rank":4,"category":"Clothing","suggestion_text":"Invest in a tailored pair of wide-leg trousers — they balance proportions and work from office to dinner.","rationale":"Wide leg creates visual balance."},
      {"rank":5,"category":"Layering","suggestion_text":"Add a lightweight knit cardigan in a neutral tone as a transitional layer — it bridges seasons and adds depth.","rationale":"Layering creates visual interest."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-aisha', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-56.jpg', _base || '/after-56.jpg', 501, 72);

  RAISE NOTICE 'Created demo card: aisha';
END IF;

-- ── 4. liam ────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'liam') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'liam', 'Liam O''Brien', 'liam@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/liam-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/liam-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/liam-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'oblong', 0.79,
    '[{"rank":1,"category":"Hairstyle","suggestion_text":"Try a textured mid-length cut with side-swept layers for a more dynamic silhouette.","rationale":"Adds width to balance longer face."},
      {"rank":2,"category":"Grooming","suggestion_text":"Try a tinted lip balm in a shade close to your natural lip color for a subtle but polished finish.","rationale":"Subtle color adds vitality."},
      {"rank":3,"category":"Accessories","suggestion_text":"Swap plastic frames for a pair of acetate tortoiseshell glasses — same comfort, ten times the style.","rationale":"Premium materials elevate any look."},
      {"rank":4,"category":"Fit","suggestion_text":"Hemming your trousers to just above the shoe creates a cleaner silhouette — small alteration, big impact.","rationale":"Clean break line elongates legs."},
      {"rank":5,"category":"Posture","suggestion_text":"Stand with shoulders back and chin parallel to the ground — better posture alone makes any outfit look 2x more intentional.","rationale":"Posture is the foundation of presence."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-liam', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-3.jpg', _base || '/after-3.jpg', 95, 11);

  RAISE NOTICE 'Created demo card: liam';
END IF;

-- ── 5. yuki ────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'yuki') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'yuki', 'Yuki Tanaka', 'yuki@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/yuki-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/yuki-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/yuki-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'round', 0.85,
    '[{"rank":1,"category":"Clothing","suggestion_text":"A structured blazer over a simple crew-neck tee creates an effortlessly put-together look for any occasion.","rationale":"Structure adds definition."},
      {"rank":2,"category":"Hairstyle","suggestion_text":"A soft curtain fringe would complement your face shape — ask your stylist for a center-parted layered cut.","rationale":"Vertical lines slim round face."},
      {"rank":3,"category":"Accessories","suggestion_text":"A minimal gold pendant necklace adds just enough detail to elevate a plain outfit without looking overdone.","rationale":"Draws eye to neckline."},
      {"rank":4,"category":"Grooming","suggestion_text":"Shape your brows with a professional wax — well-groomed brows are the single highest-impact facial change.","rationale":"Defined brows add structure."},
      {"rank":5,"category":"Footwear","suggestion_text":"A pair of Chelsea boots in suede instantly elevates jeans and a sweater from casual to date-night ready.","rationale":"Suede texture adds sophistication."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-yuki', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-60.jpg', _base || '/after-60.jpg', 267, 38);

  RAISE NOTICE 'Created demo card: yuki';
END IF;

-- ── 6. zara ────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'zara') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'zara', 'Zara Williams', 'zara@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/zara-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/zara-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/zara-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'oval', 0.93,
    '[{"rank":1,"category":"Color Palette","suggestion_text":"Deep jewel tones like burgundy, emerald, and sapphire would complement your complexion beautifully.","rationale":"Rich colors match your depth of coloring."},
      {"rank":2,"category":"Clothing","suggestion_text":"Invest in a tailored pair of wide-leg trousers — they balance proportions and work from office to dinner.","rationale":"Versatile foundation piece."},
      {"rank":3,"category":"Grooming","suggestion_text":"A consistent skincare routine with SPF 30+ daily and vitamin C serum will give you a noticeable glow within weeks.","rationale":"Consistent care compounds results."},
      {"rank":4,"category":"Hairstyle","suggestion_text":"Consider a modern shag cut with face-framing pieces to add movement and dimension.","rationale":"Movement and texture suit oval faces."},
      {"rank":5,"category":"Accessories","suggestion_text":"A quality leather watch strap in cognac or tan adds warmth and intention to any casual outfit.","rationale":"Warm leather connects outfit elements."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-zara', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-62.jpg', _base || '/after-62.jpg', 413, 56);

  RAISE NOTICE 'Created demo card: zara';
END IF;

-- ── 7. noah_k ──────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'noah_k') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'noah_k', 'Noah Kim', 'noah@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/noah-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/noah-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/noah-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'square', 0.80,
    '[{"rank":1,"category":"Fit","suggestion_text":"Your jeans are a size too large — get them tapered from the knee down for a cleaner line without sacrificing comfort.","rationale":"Proper fit is the foundation."},
      {"rank":2,"category":"Hairstyle","suggestion_text":"Try a textured mid-length cut with side-swept layers for a more dynamic silhouette.","rationale":"Texture softens strong jawline."},
      {"rank":3,"category":"Clothing","suggestion_text":"Swap the oversized tee for a well-fitted linen button-down in a warm earth tone — instant polish.","rationale":"Linen reads casual but intentional."},
      {"rank":4,"category":"Footwear","suggestion_text":"White leather sneakers with a chunky sole would modernize your casual looks — keep them clean for maximum effect.","rationale":"Clean white anchors the look."},
      {"rank":5,"category":"Layering","suggestion_text":"Add a lightweight knit cardigan in a neutral tone as a transitional layer — it bridges seasons and adds depth.","rationale":"Layers create visual complexity."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-noah', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-42.jpg', _base || '/after-42.jpg', 78, 9);

  RAISE NOTICE 'Created demo card: noah_k';
END IF;

-- ── 8. priya ───────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'priya') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'priya', 'Priya Sharma', 'priya@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/priya-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/priya-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/priya-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'heart', 0.88,
    '[{"rank":1,"category":"Accessories","suggestion_text":"Swap plastic frames for a pair of acetate tortoiseshell glasses — same comfort, ten times the style.","rationale":"Premium material upgrades the focal point of your face."},
      {"rank":2,"category":"Grooming","suggestion_text":"Try a tinted lip balm in a shade close to your natural lip color for a subtle but polished finish.","rationale":"Enhances without overpowering."},
      {"rank":3,"category":"Clothing","suggestion_text":"A structured blazer over a simple crew-neck tee creates an effortlessly put-together look.","rationale":"Structure meets comfort."},
      {"rank":4,"category":"Color Palette","suggestion_text":"Your skin undertone is warm — build around terracotta, olive, mustard, and cream instead of cool blues.","rationale":"Harmonious palette elevates everything."},
      {"rank":5,"category":"Hairstyle","suggestion_text":"A soft curtain fringe would complement your face shape beautifully.","rationale":"Softens forehead width on heart shape."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-priya', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-65.jpg', _base || '/after-65.jpg', 156, 19);

  RAISE NOTICE 'Created demo card: priya';
END IF;

-- ── 9. diego ───────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'diego') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'diego', 'Diego Santos', 'diego@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/diego-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/diego-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/diego-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'oval', 0.84,
    '[{"rank":1,"category":"Grooming","suggestion_text":"A consistent skincare routine with SPF 30+ daily and vitamin C serum will give you a noticeable glow.","rationale":"Sun protection is non-negotiable."},
      {"rank":2,"category":"Footwear","suggestion_text":"A pair of Chelsea boots in suede instantly elevates jeans and a sweater from casual to date-night ready.","rationale":"Suede adds texture without fuss."},
      {"rank":3,"category":"Fit","suggestion_text":"Hemming your trousers to just above the shoe creates a cleaner silhouette — small alteration, big impact.","rationale":"Clean break sharpens the whole look."},
      {"rank":4,"category":"Accessories","suggestion_text":"A minimal gold pendant necklace adds just enough detail to elevate a plain outfit.","rationale":"One statement piece is all you need."},
      {"rank":5,"category":"Posture","suggestion_text":"Stand with shoulders back and chin parallel to the ground — better posture alone makes any outfit look 2x more intentional.","rationale":"Posture projects confidence."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-diego', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-12.jpg', _base || '/after-12.jpg', 224, 31);

  RAISE NOTICE 'Created demo card: diego';
END IF;

-- ── 10. freya ──────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'freya') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'freya', 'Freya Jensen', 'freya@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/freya-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/freya-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/freya-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'oval', 0.90,
    '[{"rank":1,"category":"Hairstyle","suggestion_text":"Consider a modern shag cut with face-framing pieces to add movement and dimension.","rationale":"Movement suits your features."},
      {"rank":2,"category":"Clothing","suggestion_text":"Invest in a tailored pair of wide-leg trousers — they balance proportions and work from office to dinner.","rationale":"Balanced silhouette."},
      {"rank":3,"category":"Grooming","suggestion_text":"Shape your brows with a professional wax — well-groomed brows are the single highest-impact facial change.","rationale":"High ROI grooming step."},
      {"rank":4,"category":"Color Palette","suggestion_text":"Deep jewel tones like burgundy, emerald, and sapphire would complement your complexion beautifully.","rationale":"Rich tones suit cool undertones."},
      {"rank":5,"category":"Layering","suggestion_text":"Add a lightweight knit cardigan in a neutral tone as a transitional layer.","rationale":"Effortless layering."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-freya', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-67.jpg', _base || '/after-67.jpg', 388, 44);

  RAISE NOTICE 'Created demo card: freya';
END IF;

-- ── 11. kai_n ──────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'kai_n') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'kai_n', 'Kai Nakamura', 'kai@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/kai-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/kai-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/kai-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'round', 0.83,
    '[{"rank":1,"category":"Clothing","suggestion_text":"Swap the oversized tee for a well-fitted linen button-down in a warm earth tone — instant polish.","rationale":"Fit matters most."},
      {"rank":2,"category":"Hairstyle","suggestion_text":"Try a textured mid-length cut with side-swept layers for a more dynamic silhouette.","rationale":"Adds angles to round face."},
      {"rank":3,"category":"Footwear","suggestion_text":"White leather sneakers with a chunky sole would modernize your casual looks.","rationale":"Foundation of modern casual."},
      {"rank":4,"category":"Accessories","suggestion_text":"A quality leather watch strap in cognac or tan adds warmth and intention to any casual outfit.","rationale":"Small details signal intention."},
      {"rank":5,"category":"Grooming","suggestion_text":"Try a tinted lip balm in a shade close to your natural lip color for a subtle but polished finish.","rationale":"Low effort, high impact."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-kai', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-22.jpg', _base || '/after-22.jpg', 142, 17);

  RAISE NOTICE 'Created demo card: kai_n';
END IF;

-- ── 12. elena_v ────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'elena_v') THEN
  INSERT INTO users (id, username, display_name, email, email_verified, tier_id)
  VALUES (gen_random_uuid(), 'elena_v', 'Elena Volkov', 'elena@demo.nxme.ai', true, 'a0000000-0000-0000-0000-000000000001')
  RETURNING id INTO _uid;

  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/elena-selfie', 'selfie', 'cleared') RETURNING id INTO _img_selfie;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/elena-before', 'generated_before', 'cleared') RETURNING id INTO _img_before;
  INSERT INTO images (id, user_id, storage_key, image_type, status) VALUES (gen_random_uuid(), _uid, 'demo/elena-after', 'generated_after', 'cleared') RETURNING id INTO _img_after;

  INSERT INTO analyses (id, user_id, status, original_image_id, face_shape, symmetry_score, recommendations)
  VALUES (gen_random_uuid(), _uid, 'completed', _img_selfie, 'heart', 0.86,
    '[{"rank":1,"category":"Color Palette","suggestion_text":"Your skin undertone is warm — build around terracotta, olive, mustard, and cream instead of cool blues.","rationale":"Warm palette flatters warm skin."},
      {"rank":2,"category":"Accessories","suggestion_text":"A minimal gold pendant necklace adds just enough detail to elevate a plain outfit.","rationale":"Gold matches warm undertone."},
      {"rank":3,"category":"Hairstyle","suggestion_text":"A soft curtain fringe would complement your face shape — ask your stylist for a center-parted layered cut.","rationale":"Balances heart shape."},
      {"rank":4,"category":"Fit","suggestion_text":"Your jeans are a size too large — get them tapered from the knee down for a cleaner line.","rationale":"Proper fit transforms everything."},
      {"rank":5,"category":"Clothing","suggestion_text":"A structured blazer over a simple crew-neck tee creates an effortlessly put-together look.","rationale":"Easy polish."}]'::jsonb)
  RETURNING id INTO _analysis_id;

  INSERT INTO glow_up_jobs (id, idempotency_key, analysis_id, user_id, status, original_image_id, generated_image_id, identity_preserved, user_tier_at_enqueue, completed_at)
  VALUES (gen_random_uuid(), 'demo-elena', _analysis_id, _uid, 'completed', _img_before, _img_after, true, 'TRIAL', NOW()) RETURNING id INTO _job_id;

  INSERT INTO posts (user_id, glow_up_job_id, before_image_id, after_image_id, before_image_url, after_image_url, reaction_count, comment_count)
  VALUES (_uid, _job_id, _img_before, _img_after, _base || '/before-69.jpg', _base || '/after-69.jpg', 276, 35);

  RAISE NOTICE 'Created demo card: elena_v';
END IF;

END $$;

COMMIT;
