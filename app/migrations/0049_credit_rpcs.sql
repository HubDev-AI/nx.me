-- 0049_credit_rpcs.sql
-- Action-typed credit RPCs that resolve cost server-side from `plan_versions`
-- via an action-type parameter (R23). Legacy `credit_reserve`, `credit_release`,
-- `credit_commit`, `credit_refund` (0014/0019) remain intact until Unit R2
-- (entitlement service rewrite) migrates their callers.
--
-- Key behaviours:
--   * Advisory-lock domain is `hashtextextended(user_id::text, 0)` — 64-bit
--     hash to eliminate birthday collisions at ≥10k users (adversarial P2 fix,
--     Key Technical Decisions §advisory-lock).
--   * Cost is looked up via `plan_versions.{glowup_cost_milli|ada_cost_milli}`
--     using the user's active subscription's `plan_version_id`, or the seeded
--     `v1_free_default` row when no active subscription exists. Caller never
--     supplies an amount.
--   * `credit_reservations.amount` stores the actual milli-credit cost (not 1).
--     Legacy rows with amount=1 coexist.
--   * `users.locked_at IS NOT NULL` → dispute-lock; all RPCs honour it.
--     `credit_reserve` rejects with `account_locked` (SQLSTATE P0002).
--     `credit_commit` converts a commit to a release when the lock was set
--     between reserve and commit (dispute-during-in-flight path, R4). Output
--     quarantine (`dispute_review_quarantine`) is DEFERRED to v1.1 — v1
--     contract is credit refund via release; the user-facing image stays
--     visible.
--   * All functions are `SECURITY DEFINER SET search_path = public` per the
--     0021 hardening pattern. Non-service-role callers are constrained to
--     `auth.uid() = user_id`.
--
-- Dependencies: Unit 1 migration 0048 (plan_versions table, users.locked_at,
-- subscriptions.plan_version_id, extended credit_ledger.type enum with
-- 'ada_message').

-- UP

-- 1. credit_reserve: action-typed, cost resolved from plan_versions.
CREATE OR REPLACE FUNCTION public.credit_reserve(
  p_user_id UUID,
  p_reservation_id UUID,
  p_action_type TEXT
)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_plan_version_id UUID;
  v_cost            INTEGER;
  v_balance         INTEGER;
  v_locked_at       TIMESTAMPTZ;
BEGIN
  -- Fail fast on unknown action types before acquiring any lock. Guard against
  -- typos and upstream bugs — no hardcoded-cost fallback.
  IF p_action_type NOT IN ('glowup', 'ada_message') THEN
    RAISE EXCEPTION 'unknown_action_type: %', p_action_type
      USING ERRCODE = 'P0001';
  END IF;

  -- Enforce RLS-equivalent scoping for non-service-role callers. Service-role
  -- JWT has `role='service_role'` (bypasses RLS); everything else must match
  -- `auth.uid()`.
  IF auth.role() IS NOT NULL
     AND auth.role() != 'service_role'
     AND auth.uid() IS DISTINCT FROM p_user_id THEN
    RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
  END IF;

  -- Advisory lock: serializes concurrent reserves for the same user. 64-bit
  -- hash domain to eliminate cross-user collision cliffs at ≥10k users.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

  -- Dispute lock check — reject reserves for locked accounts.
  SELECT locked_at INTO v_locked_at FROM users WHERE id = p_user_id;
  IF v_locked_at IS NOT NULL THEN
    RAISE EXCEPTION 'account_locked' USING ERRCODE = 'P0001';
  END IF;

  -- Resolve effective plan_version: prefer the user's active subscription,
  -- else the seeded `v1_free_default` row.
  SELECT s.plan_version_id INTO v_plan_version_id
  FROM subscriptions s
  WHERE s.user_id = p_user_id AND s.status = 'active'
  LIMIT 1;

  IF v_plan_version_id IS NULL THEN
    SELECT id INTO v_plan_version_id
    FROM plan_versions
    WHERE version_num = 'v1_free_default'
    LIMIT 1;
  END IF;

  IF v_plan_version_id IS NULL THEN
    -- Should never happen post-0048; defensive guard for bad seeds.
    RAISE EXCEPTION 'plan_version_unresolved' USING ERRCODE = 'P0001';
  END IF;

  -- Resolve cost column based on action type.
  SELECT
    CASE p_action_type
      WHEN 'glowup'      THEN pv.glowup_cost_milli
      WHEN 'ada_message' THEN pv.ada_cost_milli
    END
  INTO v_cost
  FROM plan_versions pv
  WHERE pv.id = v_plan_version_id;

  IF v_cost IS NULL OR v_cost <= 0 THEN
    RAISE EXCEPTION 'cost_unresolved' USING ERRCODE = 'P0001';
  END IF;

  -- Balance check — SUM(delta) across the full ledger, guarded by the same
  -- advisory lock so concurrent reserves serialize.
  SELECT COALESCE(SUM(delta), 0) INTO v_balance
  FROM credit_ledger WHERE user_id = p_user_id;

  IF v_balance < v_cost THEN
    RAISE EXCEPTION 'insufficient_credits' USING ERRCODE = 'P0001';
  END IF;

  -- Insert the reservation with cost-in-milli; legacy rows with amount=1
  -- remain valid.
  INSERT INTO credit_reservations (id, user_id, amount, status, created_at)
  VALUES (p_reservation_id, p_user_id, v_cost, 'reserved', now());

  -- Deduct the cost from the ledger.
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), p_user_id, -v_cost, 'reserve', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;

-- 2. credit_commit: advisory-locked commit that honours dispute-lock by
--    converting commit → release when `users.locked_at` is set between the
--    reserve and the commit (R4 dispute-during-in-flight path).
CREATE OR REPLACE FUNCTION public.credit_commit(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id         UUID;
  v_reserved_amount INTEGER;
  v_locked_at       TIMESTAMPTZ;
BEGIN
  -- Look up user_id + amount *before* taking the advisory lock — the lock
  -- domain is keyed on user_id, which we must know first.
  SELECT user_id, amount
    INTO v_user_id, v_reserved_amount
  FROM credit_reservations
  WHERE id = p_reservation_id;

  IF v_user_id IS NULL THEN
    RETURN;  -- unknown reservation → empty result
  END IF;

  IF auth.role() IS NOT NULL
     AND auth.role() != 'service_role'
     AND auth.uid() IS DISTINCT FROM v_user_id THEN
    RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(v_user_id::text, 0));

  -- Re-read status + locked_at under the lock to avoid TOCTOU with a
  -- dispute-lock application or concurrent release.
  SELECT locked_at INTO v_locked_at FROM users WHERE id = v_user_id;

  IF v_locked_at IS NOT NULL THEN
    -- Dispute-lock set between reserve and commit → convert to release.
    -- The v1 contract: user's generated image stays visible, credit is
    -- refunded. Output-row quarantine (`dispute_review_quarantine`) is
    -- DEFERRED to v1.1 per plan (R4 over-promised a column not shipping).
    UPDATE credit_reservations
    SET status = 'released', resolved_at = now()
    WHERE id = p_reservation_id AND status = 'reserved';

    IF NOT FOUND THEN
      RETURN;  -- already resolved by another path
    END IF;

    INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
    VALUES (gen_random_uuid(), v_user_id, v_reserved_amount, 'release', p_reservation_id, now());

    RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
    RETURN;
  END IF;

  -- Happy path: flip reserved → committed; delta=0 (reserve already debited).
  UPDATE credit_reservations
  SET status = 'committed', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'reserved';

  IF NOT FOUND THEN
    RETURN;  -- already resolved
  END IF;

  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), v_user_id, 0, 'commit', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;

-- 3. credit_release: release a 'reserved' reservation; refund the exact
--    reserved amount (cost-in-milli).
CREATE OR REPLACE FUNCTION public.credit_release(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id         UUID;
  v_reserved_amount INTEGER;
BEGIN
  SELECT user_id, amount
    INTO v_user_id, v_reserved_amount
  FROM credit_reservations
  WHERE id = p_reservation_id;

  IF v_user_id IS NULL THEN
    RETURN;
  END IF;

  IF auth.role() IS NOT NULL
     AND auth.role() != 'service_role'
     AND auth.uid() IS DISTINCT FROM v_user_id THEN
    RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(v_user_id::text, 0));

  UPDATE credit_reservations
  SET status = 'released', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'reserved';

  IF NOT FOUND THEN
    RETURN;
  END IF;

  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), v_user_id, v_reserved_amount, 'release', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;

-- 4. credit_refund: flip 'committed' → 'released'; refund the reserved
--    amount. Used for post-commit fal.ai auto-refund and admin refunds.
CREATE OR REPLACE FUNCTION public.credit_refund(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id         UUID;
  v_reserved_amount INTEGER;
BEGIN
  SELECT user_id, amount
    INTO v_user_id, v_reserved_amount
  FROM credit_reservations
  WHERE id = p_reservation_id;

  IF v_user_id IS NULL THEN
    RETURN;
  END IF;

  IF auth.role() IS NOT NULL
     AND auth.role() != 'service_role'
     AND auth.uid() IS DISTINCT FROM v_user_id THEN
    RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(v_user_id::text, 0));

  UPDATE credit_reservations
  SET status = 'released', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'committed';

  IF NOT FOUND THEN
    RETURN;
  END IF;

  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), v_user_id, v_reserved_amount, 'refund', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;


-- DOWN:
-- Drop only the four action-typed functions added here. Legacy
-- credit_reserve/release/commit/refund (0014/0019) remain intact
-- until Unit R2.

DROP FUNCTION IF EXISTS public.credit_reserve(UUID, UUID, TEXT);
DROP FUNCTION IF EXISTS public.credit_commit(UUID);
DROP FUNCTION IF EXISTS public.credit_release(UUID);
DROP FUNCTION IF EXISTS public.credit_refund(UUID);
