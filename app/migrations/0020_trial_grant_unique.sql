-- Partial unique index to prevent double trial grants (C-3)
CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_ledger_trial_grant
  ON credit_ledger (user_id)
  WHERE type = 'trial_grant';

-- DOWN:
DROP INDEX IF EXISTS uq_credit_ledger_trial_grant;
