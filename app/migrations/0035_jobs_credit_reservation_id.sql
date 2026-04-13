-- Add credit_reservation_id to jobs (omitted from 0034 when glow_up_jobs was renamed to jobs)
ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS credit_reservation_id UUID REFERENCES credit_reservations(id);

-- DOWN:
ALTER TABLE jobs DROP COLUMN IF EXISTS credit_reservation_id;
