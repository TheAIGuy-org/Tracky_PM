-- ==========================================
-- MIGRATION 006: Production Constraints & Critical Fixes
-- ==========================================
-- This migration adds constraints for production readiness
-- Run AFTER 005_pm_resource_production.sql
-- ==========================================


-- ==========================================
-- STEP 1: CRIT_003 - Prevent Duplicate Alerts (Race Condition)
-- ==========================================
-- Unique index prevents concurrent processes from creating duplicate alerts

DROP INDEX IF EXISTS idx_unique_pending_alert;

CREATE UNIQUE INDEX idx_unique_pending_alert 
ON alerts(work_item_id, deadline_date, alert_type) 
WHERE status NOT IN ('EXPIRED', 'CANCELLED');

COMMENT ON INDEX idx_unique_pending_alert IS 
'CRIT_003: Prevents duplicate alerts for same work item/deadline/type combination';


-- ==========================================
-- STEP 2: CRIT_002 - Manual Intervention Flag
-- ==========================================
-- Flag for alerts that couldn't find a recipient

ALTER TABLE alerts 
ADD COLUMN IF NOT EXISTS requires_manual_intervention boolean DEFAULT false;

COMMENT ON COLUMN alerts.requires_manual_intervention IS 
'CRIT_002: True when no recipient could be found and manual action is required';


-- ==========================================
-- STEP 3: CRIT_008 - Response Token Tracking
-- ==========================================
-- Track token usage to prevent reuse

-- Add token tracking to responses
ALTER TABLE work_item_responses
ADD COLUMN IF NOT EXISTS response_token_id uuid REFERENCES response_tokens(id),
ADD COLUMN IF NOT EXISTS response_version integer DEFAULT 1,
ADD COLUMN IF NOT EXISTS superseded_by_response_version integer,
ADD COLUMN IF NOT EXISTS submitted_at timestamptz DEFAULT now();

-- Index for finding latest response
DROP INDEX IF EXISTS idx_responses_latest;
CREATE INDEX idx_responses_latest 
ON work_item_responses(work_item_id, is_latest) 
WHERE is_latest = true;

-- Index for version ordering
DROP INDEX IF EXISTS idx_responses_version;
CREATE INDEX idx_responses_version 
ON work_item_responses(work_item_id, response_version DESC);

-- Add used tracking to response_tokens
ALTER TABLE response_tokens
ADD COLUMN IF NOT EXISTS used_at timestamptz,
ADD COLUMN IF NOT EXISTS used_by_response_id uuid;

COMMENT ON COLUMN response_tokens.used_at IS 
'CRIT_008: Timestamp when token was consumed by a response';

COMMENT ON COLUMN response_tokens.used_by_response_id IS 
'CRIT_008: Links to the response that consumed this token';


-- ==========================================
-- STEP 4: CRIT_006 - Cascade Operations Tracking
-- ==========================================
-- Track cascade updates for rollback capability

CREATE TABLE IF NOT EXISTS cascade_operations (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- Primary change
  primary_work_item_id uuid NOT NULL REFERENCES work_items(id),
  change_type text NOT NULL CHECK (change_type IN ('DELAY', 'DATE_CHANGE', 'CANCELLATION')),
  
  -- Trigger info
  triggered_by text NOT NULL,  -- 'approval', 'import', 'manual'
  triggered_by_user text,
  triggered_by_response_id uuid REFERENCES work_item_responses(id),
  
  -- Operation status
  status text NOT NULL DEFAULT 'IN_PROGRESS' CHECK (status IN (
    'IN_PROGRESS', 'COMPLETED', 'FAILED', 'ROLLED_BACK'
  )),
  
  -- Affected items (stored as JSON for flexibility)
  affected_items jsonb NOT NULL DEFAULT '[]',
  
  -- Rollback info
  rollback_data jsonb,  -- Original values before cascade
  rolled_back_at timestamptz,
  rollback_reason text,
  
  -- Error tracking
  error_message text,
  failed_items jsonb,
  
  -- Timestamps
  started_at timestamptz DEFAULT now(),
  completed_at timestamptz,
  
  created_at timestamptz DEFAULT now()
);

-- Only create indexes if they don't exist
DROP INDEX IF EXISTS idx_cascade_operations_primary;
CREATE INDEX idx_cascade_operations_primary 
ON cascade_operations(primary_work_item_id);

DROP INDEX IF EXISTS idx_cascade_operations_status;
CREATE INDEX idx_cascade_operations_status 
ON cascade_operations(status, started_at DESC);

-- RLS for cascade_operations
ALTER TABLE cascade_operations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow read cascade operations" ON cascade_operations;
CREATE POLICY "Allow read cascade operations" ON cascade_operations
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow admin write cascade operations" ON cascade_operations;
CREATE POLICY "Allow admin write cascade operations" ON cascade_operations
  FOR ALL USING (auth.role() = 'service_role');

GRANT ALL ON cascade_operations TO authenticated;
GRANT SELECT ON cascade_operations TO anon;


-- ==========================================
-- STEP 5: Business Hours Helper Functions
-- ==========================================
-- Calculate escalation timeouts respecting business hours

CREATE OR REPLACE FUNCTION is_business_hour(
  check_time timestamptz,
  p_timezone text DEFAULT 'UTC'
)
RETURNS boolean AS $$
DECLARE
  local_time timestamptz;
  day_of_week int;
  hour_of_day int;
BEGIN
  -- Convert to local timezone
  local_time := check_time AT TIME ZONE p_timezone;
  day_of_week := EXTRACT(DOW FROM local_time);  -- 0=Sunday, 6=Saturday
  hour_of_day := EXTRACT(HOUR FROM local_time);
  
  -- Check if weekend
  IF day_of_week IN (0, 6) THEN
    RETURN false;
  END IF;
  
  -- Check if holiday (from holiday_calendar if exists)
  IF EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_name = 'holiday_calendar'
  ) THEN
    IF EXISTS (
      SELECT 1 FROM holiday_calendar 
      WHERE holiday_date = local_time::date 
      AND (applies_to_programs IS NULL OR applies_to_programs = '{}')
    ) THEN
      RETURN false;
    END IF;
  END IF;
  
  -- Check business hours (9 AM - 5 PM)
  IF hour_of_day < 9 OR hour_of_day >= 17 THEN
    RETURN false;
  END IF;
  
  RETURN true;
END;
$$ LANGUAGE plpgsql STABLE;


CREATE OR REPLACE FUNCTION add_business_hours(
  start_time timestamptz,
  hours_to_add int,
  p_timezone text DEFAULT 'UTC'
)
RETURNS timestamptz AS $$
DECLARE
  calc_time timestamptz := start_time;
  business_hours_added int := 0;
BEGIN
  -- Add hours one at a time, skipping non-business hours
  WHILE business_hours_added < hours_to_add LOOP
    calc_time := calc_time + interval '1 hour';
    
    IF is_business_hour(calc_time, p_timezone) THEN
      business_hours_added := business_hours_added + 1;
    END IF;
    
    -- Safety: Don't loop forever (max 30 days)
    IF calc_time > start_time + interval '30 days' THEN
      EXIT;
    END IF;
  END LOOP;
  
  RETURN calc_time;
END;
$$ LANGUAGE plpgsql STABLE;


-- ==========================================
-- STEP 6: Safe Alert Creation (CRIT_003)
-- ==========================================
-- Handles race conditions gracefully

CREATE OR REPLACE FUNCTION create_alert_safe(
  p_work_item_id uuid,
  p_deadline_date date,
  p_alert_type text,
  p_intended_recipient_id uuid,
  p_actual_recipient_id uuid,
  p_urgency text DEFAULT 'NORMAL',
  p_escalation_level int DEFAULT 0,
  p_notification_metadata jsonb DEFAULT '{}'
)
RETURNS TABLE (
  alert_id uuid,
  is_new boolean,
  message text
) AS $$
DECLARE
  v_existing_id uuid;
  v_new_id uuid;
BEGIN
  -- Check for existing active alert
  SELECT id INTO v_existing_id
  FROM alerts
  WHERE work_item_id = p_work_item_id
    AND deadline_date = p_deadline_date
    AND alert_type = p_alert_type
    AND status NOT IN ('EXPIRED', 'CANCELLED')
  LIMIT 1;
  
  IF v_existing_id IS NOT NULL THEN
    -- Return existing alert
    RETURN QUERY SELECT v_existing_id, false, 'Alert already exists';
    RETURN;
  END IF;
  
  -- Try to insert new alert
  BEGIN
    INSERT INTO alerts (
      work_item_id, deadline_date, alert_type, 
      intended_recipient_id, actual_recipient_id,
      urgency, escalation_level, status, notification_metadata
    ) VALUES (
      p_work_item_id, p_deadline_date, p_alert_type,
      p_intended_recipient_id, p_actual_recipient_id,
      p_urgency, p_escalation_level, 'PENDING', p_notification_metadata
    )
    RETURNING id INTO v_new_id;
    
    RETURN QUERY SELECT v_new_id, true, 'Alert created';
    
  EXCEPTION WHEN unique_violation THEN
    -- Race condition: another process created the alert
    SELECT id INTO v_existing_id
    FROM alerts
    WHERE work_item_id = p_work_item_id
      AND deadline_date = p_deadline_date
      AND alert_type = p_alert_type
      AND status NOT IN ('EXPIRED', 'CANCELLED')
    LIMIT 1;
    
    RETURN QUERY SELECT v_existing_id, false, 'Alert created by concurrent process';
  END;
END;
$$ LANGUAGE plpgsql;


-- ==========================================
-- STEP 7: Safe Response Processing (CRIT_008)
-- ==========================================
-- Handle token reuse prevention

CREATE OR REPLACE FUNCTION process_response_safe(
  p_alert_id uuid,
  p_work_item_id uuid,
  p_responder_id uuid,
  p_token_id uuid,
  p_reported_status text,
  p_reason_category text DEFAULT NULL,
  p_reason_details jsonb DEFAULT NULL,
  p_comment text DEFAULT NULL,
  p_proposed_new_date date DEFAULT NULL
)
RETURNS TABLE (
  response_id uuid,
  response_version int,
  is_duplicate boolean,
  message text
) AS $$
DECLARE
  v_token_used boolean;
  v_current_version int;
  v_new_version int;
  v_response_id uuid;
  v_latest_response_id uuid;
BEGIN
  -- Check if token already used
  SELECT revoked INTO v_token_used
  FROM response_tokens
  WHERE id = p_token_id;
  
  IF v_token_used IS NULL THEN
    RETURN QUERY SELECT NULL::uuid, 0, false, 'Token not found';
    RETURN;
  END IF;
  
  IF v_token_used THEN
    RETURN QUERY SELECT NULL::uuid, 0, true, 'Token already used';
    RETURN;
  END IF;
  
  -- Get current version
  SELECT COALESCE(MAX(response_version), 0), 
         (SELECT id FROM work_item_responses WHERE work_item_id = p_work_item_id AND is_latest = true LIMIT 1)
  INTO v_current_version, v_latest_response_id
  FROM work_item_responses
  WHERE work_item_id = p_work_item_id;
  
  v_new_version := v_current_version + 1;
  
  -- Start transaction-like behavior
  -- 1. Mark previous response as not latest
  IF v_latest_response_id IS NOT NULL THEN
    UPDATE work_item_responses
    SET is_latest = false,
        superseded_by_response_version = v_new_version
    WHERE id = v_latest_response_id;
  END IF;
  
  -- 2. Create new response
  INSERT INTO work_item_responses (
    alert_id, work_item_id, responder_resource_id, response_token_id,
    response_version, is_latest, reported_status,
    reason_category, reason_details, comment, proposed_new_date,
    submitted_at
  ) VALUES (
    p_alert_id, p_work_item_id, p_responder_id, p_token_id,
    v_new_version, true, p_reported_status,
    p_reason_category, p_reason_details, p_comment, p_proposed_new_date,
    now()
  )
  RETURNING id INTO v_response_id;
  
  -- 3. Revoke token
  UPDATE response_tokens
  SET revoked = true,
      used_at = now(),
      used_by_response_id = v_response_id
  WHERE id = p_token_id;
  
  -- 4. Update alert status
  UPDATE alerts
  SET status = 'RESPONDED',
      responded_at = now()
  WHERE id = p_alert_id;
  
  RETURN QUERY SELECT v_response_id, v_new_version, false, 'Response recorded';
END;
$$ LANGUAGE plpgsql;


-- ==========================================
-- STEP 8: Add Escalation Email Fallback Setting
-- ==========================================
-- Insert only if not exists

INSERT INTO organization_settings (key, value, description)
SELECT 'ops_escalation_email', 'null'::jsonb, 'Fallback email for critical alerts when no PM available'
WHERE NOT EXISTS (
  SELECT 1 FROM organization_settings WHERE key = 'ops_escalation_email'
);


-- ==========================================
-- DONE
-- ==========================================
-- Migration 006 completed successfully
-- Critical fixes: CRIT_002, CRIT_003, CRIT_006, CRIT_008

SELECT 'Migration 006 completed successfully' as status;
