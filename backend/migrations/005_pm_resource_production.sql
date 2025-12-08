-- ==========================================
-- MIGRATION 005: PM Resource ID & Production Readiness
-- ==========================================
-- Adds PM resource ID to programs table for proper escalation
-- and additional fields for production readiness
-- ==========================================


-- ==========================================
-- STEP 1: Add PM Resource ID to Programs
-- ==========================================
-- This enables Level 3 escalation to reach the correct PM

ALTER TABLE programs 
ADD COLUMN IF NOT EXISTS pm_resource_id uuid REFERENCES resources(id),
ADD COLUMN IF NOT EXISTS secondary_pm_resource_id uuid REFERENCES resources(id);

-- Comment explaining the fields
COMMENT ON COLUMN programs.pm_resource_id IS 'Primary PM responsible for this program - receives Level 3 escalations';
COMMENT ON COLUMN programs.secondary_pm_resource_id IS 'Backup PM when primary is unavailable';

-- Index for PM lookup
CREATE INDEX IF NOT EXISTS idx_programs_pm ON programs(pm_resource_id) WHERE pm_resource_id IS NOT NULL;


-- ==========================================
-- STEP 2: Add Default PM for Organization
-- ==========================================
-- For cases where no PM is assigned to a program

CREATE TABLE IF NOT EXISTS organization_settings (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  key text UNIQUE NOT NULL,
  value jsonb NOT NULL,
  description text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Insert default PM setting
INSERT INTO organization_settings (key, value, description) 
VALUES (
  'default_pm_resource_id',
  'null'::jsonb,
  'Default PM resource ID for programs without an assigned PM'
) ON CONFLICT (key) DO NOTHING;

INSERT INTO organization_settings (key, value, description)
VALUES (
  'escalation_email_fallback',
  '"admin@example.com"'::jsonb,
  'Fallback email when no PM is available for escalation'
) ON CONFLICT (key) DO NOTHING;


-- ==========================================
-- STEP 3: Job Execution Tracking Table
-- ==========================================
-- For monitoring scheduled job executions

CREATE TABLE IF NOT EXISTS job_executions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  job_id text NOT NULL,
  job_name text,
  status text NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
  started_at timestamptz DEFAULT now(),
  completed_at timestamptz,
  duration_seconds numeric,
  result jsonb,
  error text,
  
  -- Metrics
  items_processed int DEFAULT 0,
  items_failed int DEFAULT 0,
  
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_executions_job ON job_executions(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_executions_status ON job_executions(status, started_at DESC);

-- Partition by month for large deployments (optional)
-- CREATE INDEX IF NOT EXISTS idx_job_executions_time ON job_executions(started_at);


-- ==========================================
-- STEP 4: Notification Log Table
-- ==========================================
-- Track all notification delivery attempts

CREATE TABLE IF NOT EXISTS notification_log (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- Reference
  alert_id uuid REFERENCES alerts(id) ON DELETE SET NULL,
  response_id uuid REFERENCES work_item_responses(id) ON DELETE SET NULL,
  
  -- Recipient
  recipient_email text NOT NULL,
  recipient_name text,
  
  -- Notification details
  notification_type text NOT NULL CHECK (notification_type IN (
    'STATUS_CHECK', 'RESPONSE_CONFIRMATION', 'APPROVAL_REQUEST', 
    'ESCALATION', 'NO_RECIPIENT', 'REMINDER', 'APPROVAL_RESULT'
  )),
  channel text NOT NULL CHECK (channel IN ('EMAIL', 'SLACK', 'BOTH')),
  
  -- Content
  subject text,
  template_name text,
  
  -- Delivery status
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN (
    'PENDING', 'SENT', 'DELIVERED', 'OPENED', 'CLICKED', 'FAILED', 'BOUNCED'
  )),
  
  -- Provider info
  provider text,                        -- 'sendgrid', 'smtp', 'slack'
  external_message_id text,             -- Provider's message ID
  
  -- Error handling
  error_message text,
  retry_count int DEFAULT 0,
  max_retries int DEFAULT 3,
  next_retry_at timestamptz,
  
  -- Timestamps
  created_at timestamptz DEFAULT now(),
  sent_at timestamptz,
  delivered_at timestamptz,
  opened_at timestamptz,
  
  -- Metadata
  metadata jsonb
);

CREATE INDEX IF NOT EXISTS idx_notification_log_alert ON notification_log(alert_id);
CREATE INDEX IF NOT EXISTS idx_notification_log_status ON notification_log(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_log_retry ON notification_log(next_retry_at) 
  WHERE status = 'FAILED' AND retry_count < max_retries;


-- ==========================================
-- STEP 5: Update Escalation Chain Function
-- ==========================================
-- Add PM lookup to escalation chain

CREATE OR REPLACE FUNCTION get_escalation_chain_v2(
  p_resource_id uuid,
  p_program_id uuid DEFAULT NULL
)
RETURNS TABLE (
  escalation_level int,
  target_type text,
  target_resource_id uuid,
  target_resource_name text,
  target_email text,
  is_available boolean,
  availability_status text
) AS $$
DECLARE
  v_resource record;
  v_backup record;
  v_manager record;
  v_pm record;
  v_default_pm_id uuid;
BEGIN
  -- Get primary resource
  SELECT * INTO v_resource FROM resources WHERE id = p_resource_id;
  
  IF v_resource IS NULL THEN
    RETURN;
  END IF;
  
  -- Level 0: Primary
  RETURN QUERY SELECT 
    0::int,
    'PRIMARY'::text,
    v_resource.id,
    v_resource.name,
    COALESCE(v_resource.notification_email, v_resource.email),
    v_resource.availability_status = 'ACTIVE',
    v_resource.availability_status;
  
  -- Level 1: Backup
  IF v_resource.backup_resource_id IS NOT NULL THEN
    SELECT * INTO v_backup FROM resources WHERE id = v_resource.backup_resource_id;
    
    IF v_backup IS NOT NULL THEN
      RETURN QUERY SELECT 
        1::int,
        'BACKUP'::text,
        v_backup.id,
        v_backup.name,
        COALESCE(v_backup.notification_email, v_backup.email),
        v_backup.availability_status = 'ACTIVE',
        v_backup.availability_status;
    END IF;
  END IF;
  
  -- Level 2: Manager
  IF v_resource.manager_id IS NOT NULL THEN
    SELECT * INTO v_manager FROM resources WHERE id = v_resource.manager_id;
    
    IF v_manager IS NOT NULL THEN
      RETURN QUERY SELECT 
        2::int,
        'MANAGER'::text,
        v_manager.id,
        v_manager.name,
        COALESCE(v_manager.notification_email, v_manager.email),
        v_manager.availability_status = 'ACTIVE',
        v_manager.availability_status;
    END IF;
  END IF;
  
  -- Level 3: PM (from program or default)
  IF p_program_id IS NOT NULL THEN
    SELECT r.* INTO v_pm 
    FROM resources r
    JOIN programs p ON p.pm_resource_id = r.id
    WHERE p.id = p_program_id;
  END IF;
  
  -- Try secondary PM if primary unavailable
  IF v_pm IS NULL OR v_pm.availability_status != 'ACTIVE' THEN
    IF p_program_id IS NOT NULL THEN
      SELECT r.* INTO v_pm
      FROM resources r
      JOIN programs p ON p.secondary_pm_resource_id = r.id
      WHERE p.id = p_program_id;
    END IF;
  END IF;
  
  -- Try default PM from org settings
  IF v_pm IS NULL THEN
    SELECT (value::text)::uuid INTO v_default_pm_id
    FROM organization_settings
    WHERE key = 'default_pm_resource_id'
    AND value != 'null'::jsonb;
    
    IF v_default_pm_id IS NOT NULL THEN
      SELECT * INTO v_pm FROM resources WHERE id = v_default_pm_id;
    END IF;
  END IF;
  
  IF v_pm IS NOT NULL THEN
    RETURN QUERY SELECT 
      3::int,
      'PM'::text,
      v_pm.id,
      v_pm.name,
      COALESCE(v_pm.notification_email, v_pm.email),
      v_pm.availability_status = 'ACTIVE',
      v_pm.availability_status;
  END IF;
  
END;
$$ LANGUAGE plpgsql STABLE;


-- ==========================================
-- STEP 6: Get PM for Program Function
-- ==========================================
-- Helper function to get PM details for a program

CREATE OR REPLACE FUNCTION get_program_pm(p_program_id uuid)
RETURNS TABLE (
  pm_resource_id uuid,
  pm_name text,
  pm_email text,
  is_available boolean
) AS $$
DECLARE
  v_pm record;
  v_default_pm_id uuid;
BEGIN
  -- Try primary PM
  SELECT r.id, r.name, COALESCE(r.notification_email, r.email) as email, 
         r.availability_status = 'ACTIVE' as available
  INTO v_pm
  FROM programs p
  JOIN resources r ON r.id = p.pm_resource_id
  WHERE p.id = p_program_id;
  
  IF v_pm IS NOT NULL AND v_pm.available THEN
    RETURN QUERY SELECT v_pm.id, v_pm.name, v_pm.email, v_pm.available;
    RETURN;
  END IF;
  
  -- Try secondary PM
  SELECT r.id, r.name, COALESCE(r.notification_email, r.email) as email,
         r.availability_status = 'ACTIVE' as available
  INTO v_pm
  FROM programs p
  JOIN resources r ON r.id = p.secondary_pm_resource_id
  WHERE p.id = p_program_id;
  
  IF v_pm IS NOT NULL AND v_pm.available THEN
    RETURN QUERY SELECT v_pm.id, v_pm.name, v_pm.email, v_pm.available;
    RETURN;
  END IF;
  
  -- Try default PM
  SELECT (value::text)::uuid INTO v_default_pm_id
  FROM organization_settings
  WHERE key = 'default_pm_resource_id'
  AND value != 'null'::jsonb;
  
  IF v_default_pm_id IS NOT NULL THEN
    SELECT r.id, r.name, COALESCE(r.notification_email, r.email) as email,
           r.availability_status = 'ACTIVE' as available
    INTO v_pm
    FROM resources r
    WHERE r.id = v_default_pm_id;
    
    IF v_pm IS NOT NULL THEN
      RETURN QUERY SELECT v_pm.id, v_pm.name, v_pm.email, v_pm.available;
      RETURN;
    END IF;
  END IF;
  
  -- Return null if no PM found
  RETURN;
END;
$$ LANGUAGE plpgsql STABLE;


-- ==========================================
-- STEP 7: RLS Policies for New Tables
-- ==========================================

ALTER TABLE organization_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_log ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to read org settings
CREATE POLICY "Allow read org settings" ON organization_settings
  FOR SELECT USING (true);

-- Allow service role to modify org settings
CREATE POLICY "Allow admin write org settings" ON organization_settings
  FOR ALL USING (auth.role() = 'service_role');

-- Allow authenticated users to read job executions
CREATE POLICY "Allow read job executions" ON job_executions
  FOR SELECT USING (true);

-- Allow service role to write job executions
CREATE POLICY "Allow admin write job executions" ON job_executions
  FOR ALL USING (auth.role() = 'service_role');

-- Allow authenticated users to read notification log
CREATE POLICY "Allow read notification log" ON notification_log
  FOR SELECT USING (true);

-- Allow service role to write notification log
CREATE POLICY "Allow admin write notification log" ON notification_log
  FOR ALL USING (auth.role() = 'service_role');


-- ==========================================
-- STEP 8: Grant Permissions
-- ==========================================

GRANT ALL ON organization_settings TO authenticated;
GRANT ALL ON job_executions TO authenticated;
GRANT ALL ON notification_log TO authenticated;

GRANT SELECT ON organization_settings TO anon;
GRANT SELECT ON job_executions TO anon;
GRANT SELECT ON notification_log TO anon;


-- ==========================================
-- STEP 9: Add Config Validation Trigger
-- ==========================================
-- Validate email settings exist before allowing email notifications

CREATE OR REPLACE FUNCTION validate_notification_config()
RETURNS trigger AS $$
BEGIN
  -- Check if notification channel is EMAIL but no email configured
  IF NEW.notification_channel = 'EMAIL' THEN
    -- Get recipient email
    IF NEW.actual_recipient_id IS NOT NULL THEN
      PERFORM 1 FROM resources 
      WHERE id = NEW.actual_recipient_id 
      AND (email IS NOT NULL OR notification_email IS NOT NULL);
      
      IF NOT FOUND THEN
        RAISE WARNING 'Alert % has no recipient email configured', NEW.id;
      END IF;
    END IF;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS validate_alert_notification ON alerts;
CREATE TRIGGER validate_alert_notification
BEFORE INSERT OR UPDATE ON alerts
FOR EACH ROW
EXECUTE FUNCTION validate_notification_config();


-- ==========================================
-- STEP 10: CRITICAL DATABASE CONSTRAINTS (CRIT_003, CRIT_004)
-- ==========================================
-- These constraints prevent critical production issues

-- CRIT_003: Prevent duplicate alerts for same work item/deadline/type
-- This unique index prevents race conditions where multiple processes
-- try to create the same alert simultaneously
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_pending_alert 
ON alerts(work_item_id, deadline_date, alert_type) 
WHERE status NOT IN ('EXPIRED', 'CANCELLED');

-- CRIT_004: Ensure all timestamps are UTC (timezone-aware)
-- PostgreSQL stores timestamptz in UTC, this validates input format
-- Note: This is enforced at application level too, this is defense-in-depth

-- CRIT_002: Add constraint to ensure critical alerts have recipients
-- For ESCALATION type alerts at level 3 (PM level), must have a recipient
-- OR be flagged as requiring manual intervention
ALTER TABLE alerts 
ADD COLUMN IF NOT EXISTS requires_manual_intervention boolean DEFAULT false;

-- Add comment explaining the field
COMMENT ON COLUMN alerts.requires_manual_intervention IS 
'True when no recipient could be found and manual action is required';


-- ==========================================
-- STEP 11: Response Token Tracking (CRIT_008)
-- ==========================================
-- Track token usage to prevent reuse

-- Add token tracking to responses if not exists
ALTER TABLE work_item_responses
ADD COLUMN IF NOT EXISTS response_token_id uuid REFERENCES response_tokens(id),
ADD COLUMN IF NOT EXISTS response_version integer DEFAULT 1,
ADD COLUMN IF NOT EXISTS superseded_by_response_version integer,
ADD COLUMN IF NOT EXISTS submitted_at timestamptz DEFAULT now();

-- Index for finding latest response
CREATE INDEX IF NOT EXISTS idx_responses_latest 
ON work_item_responses(work_item_id, is_latest) 
WHERE is_latest = true;

-- Index for version ordering
CREATE INDEX IF NOT EXISTS idx_responses_version 
ON work_item_responses(work_item_id, response_version DESC);

-- Add used tracking to response_tokens
ALTER TABLE response_tokens
ADD COLUMN IF NOT EXISTS used_at timestamptz,
ADD COLUMN IF NOT EXISTS used_by_response_id uuid;


-- ==========================================
-- STEP 12: Cascade Tracking (CRIT_006)
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

CREATE INDEX IF NOT EXISTS idx_cascade_operations_primary 
ON cascade_operations(primary_work_item_id);

CREATE INDEX IF NOT EXISTS idx_cascade_operations_status 
ON cascade_operations(status, started_at DESC);


-- ==========================================
-- STEP 13: Business Hours Helper Functions (CRIT_004, SCENARIO 7)
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
  
  -- Check if holiday (from holiday_calendar)
  IF EXISTS (
    SELECT 1 FROM holiday_calendar 
    WHERE holiday_date = local_time::date 
    AND (applies_to_programs IS NULL OR applies_to_programs = '{}')
  ) THEN
    RETURN false;
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
  current_time timestamptz := start_time;
  business_hours_added int := 0;
BEGIN
  -- Add hours one at a time, skipping non-business hours
  WHILE business_hours_added < hours_to_add LOOP
    current_time := current_time + interval '1 hour';
    
    IF is_business_hour(current_time, p_timezone) THEN
      business_hours_added := business_hours_added + 1;
    END IF;
    
    -- Safety: Don't loop forever (max 30 days)
    IF current_time > start_time + interval '30 days' THEN
      EXIT;
    END IF;
  END LOOP;
  
  RETURN current_time;
END;
$$ LANGUAGE plpgsql STABLE;


-- ==========================================
-- STEP 14: Alert Deduplication Helper (CRIT_003)
-- ==========================================
-- Safe alert creation with deduplication

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
-- STEP 15: Response Deduplication (CRIT_008, SCENARIO 9)
-- ==========================================
-- Handle concurrent responses safely

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
