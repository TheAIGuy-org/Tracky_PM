-- ==========================================
-- MIGRATION 004: Proactive Execution Tracking Loop
-- ==========================================
-- The "Soul" of Tracky PM - Proactive risk detection system
-- 
-- This migration implements:
-- 1. Enhanced Resource Entity (manager hierarchy, availability, escalation)
-- 2. Alert Entity (lifecycle tracking for notifications)
-- 3. WorkItemResponse Entity (captures human input with versioning)
-- 4. Holiday Calendar (business day calculations)
-- 5. Escalation Policy Configuration
-- 6. Magic Link Token System
-- ==========================================


-- ==========================================
-- STEP 1: Enhanced Resource Entity
-- ==========================================
-- Adds manager hierarchy, availability tracking, and escalation support

-- 1A. Add manager hierarchy and availability columns
ALTER TABLE resources 
ADD COLUMN IF NOT EXISTS manager_id uuid REFERENCES resources(id),
ADD COLUMN IF NOT EXISTS backup_resource_id uuid REFERENCES resources(id),
ADD COLUMN IF NOT EXISTS availability_status text DEFAULT 'ACTIVE' 
  CHECK (availability_status IN ('ACTIVE', 'ON_LEAVE', 'UNAVAILABLE', 'PARTIAL')),
ADD COLUMN IF NOT EXISTS leave_start_date date,
ADD COLUMN IF NOT EXISTS leave_end_date date,
ADD COLUMN IF NOT EXISTS timezone text DEFAULT 'UTC',
ADD COLUMN IF NOT EXISTS notification_email text,
ADD COLUMN IF NOT EXISTS slack_user_id text,
ADD COLUMN IF NOT EXISTS preferred_notification_channel text DEFAULT 'EMAIL'
  CHECK (preferred_notification_channel IN ('EMAIL', 'SLACK', 'BOTH'));

-- 1B. Index for manager hierarchy queries
CREATE INDEX IF NOT EXISTS idx_resources_manager ON resources(manager_id) WHERE manager_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_resources_backup ON resources(backup_resource_id) WHERE backup_resource_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_resources_availability ON resources(availability_status);

-- 1C. Function to detect circular manager references
CREATE OR REPLACE FUNCTION check_manager_circular_reference()
RETURNS TRIGGER AS $$
DECLARE
  current_manager_id uuid;
  depth int := 0;
  max_depth int := 20;
BEGIN
  -- Check if setting manager_id would create a cycle
  IF NEW.manager_id IS NOT NULL THEN
    current_manager_id := NEW.manager_id;
    
    WHILE current_manager_id IS NOT NULL AND depth < max_depth LOOP
      -- If we find ourselves in the chain, it's a cycle
      IF current_manager_id = NEW.id THEN
        RAISE EXCEPTION 'Circular manager reference detected: Resource % cannot have % as manager (creates cycle)', 
          NEW.external_id, 
          (SELECT external_id FROM resources WHERE id = NEW.manager_id);
      END IF;
      
      -- Move up the chain
      SELECT manager_id INTO current_manager_id 
      FROM resources 
      WHERE id = current_manager_id;
      
      depth := depth + 1;
    END LOOP;
  END IF;
  
  -- Same check for backup_resource_id
  IF NEW.backup_resource_id IS NOT NULL AND NEW.backup_resource_id = NEW.id THEN
    RAISE EXCEPTION 'Resource cannot be its own backup';
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS check_manager_circular_trigger ON resources;
CREATE TRIGGER check_manager_circular_trigger
BEFORE INSERT OR UPDATE OF manager_id, backup_resource_id ON resources
FOR EACH ROW
EXECUTE FUNCTION check_manager_circular_reference();


-- ==========================================
-- STEP 2: Holiday Calendar Entity
-- ==========================================
-- Supports business day calculations with multi-region holidays

CREATE TABLE IF NOT EXISTS holiday_calendar (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- Holiday identification
  name text NOT NULL,
  holiday_date date NOT NULL,
  
  -- Scope (which teams/regions observe this holiday)
  country_code text,                    -- 'US', 'IN', 'GB', NULL for company-wide
  region_code text,                     -- 'CA', 'NY', NULL for nationwide
  
  -- Type
  holiday_type text DEFAULT 'COMPANY'
    CHECK (holiday_type IN ('COMPANY', 'NATIONAL', 'REGIONAL', 'OPTIONAL')),
  
  -- Recurrence
  is_recurring boolean DEFAULT false,
  recurrence_rule text,                 -- 'YEARLY:MM-DD' or 'YEARLY:LAST_MON_MAY' etc.
  
  -- Metadata
  created_at timestamptz DEFAULT now(),
  created_by text,
  
  -- Prevent duplicate holidays on same date for same region
  UNIQUE(holiday_date, country_code, region_code)
);

CREATE INDEX IF NOT EXISTS idx_holiday_calendar_date ON holiday_calendar(holiday_date);
CREATE INDEX IF NOT EXISTS idx_holiday_calendar_country ON holiday_calendar(country_code, holiday_date);

-- Insert common US holidays for 2025-2026 as defaults
INSERT INTO holiday_calendar (name, holiday_date, country_code, holiday_type, is_recurring) VALUES
  ('New Year''s Day', '2025-01-01', 'US', 'NATIONAL', true),
  ('Martin Luther King Jr. Day', '2025-01-20', 'US', 'NATIONAL', false),
  ('Presidents Day', '2025-02-17', 'US', 'NATIONAL', false),
  ('Memorial Day', '2025-05-26', 'US', 'NATIONAL', false),
  ('Independence Day', '2025-07-04', 'US', 'NATIONAL', true),
  ('Labor Day', '2025-09-01', 'US', 'NATIONAL', false),
  ('Thanksgiving', '2025-11-27', 'US', 'NATIONAL', false),
  ('Christmas Day', '2025-12-25', 'US', 'NATIONAL', true),
  ('New Year''s Day', '2026-01-01', 'US', 'NATIONAL', true)
ON CONFLICT (holiday_date, country_code, region_code) DO NOTHING;


-- ==========================================
-- STEP 3: Alert Entity
-- ==========================================
-- Tracks the complete lifecycle of status check notifications

CREATE TABLE IF NOT EXISTS alerts (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- What this alert is about
  work_item_id uuid NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
  deadline_date date NOT NULL,          -- The deadline this alert is checking
  
  -- Who received it
  intended_recipient_id uuid NOT NULL REFERENCES resources(id),  -- Original assignee
  actual_recipient_id uuid REFERENCES resources(id),             -- Who actually got it (backup, manager)
  escalation_reason text,               -- 'PRIMARY_UNAVAILABLE', 'NO_RESPONSE', 'MANUAL'
  
  -- Alert type and level
  alert_type text NOT NULL DEFAULT 'STATUS_CHECK'
    CHECK (alert_type IN ('STATUS_CHECK', 'ESCALATION', 'BLOCKER_REPORT', 'APPROVAL_REQUEST', 'NOTIFICATION')),
  escalation_level int DEFAULT 0,       -- 0=Primary, 1=Backup, 2=Manager, 3=PM
  urgency text DEFAULT 'NORMAL'
    CHECK (urgency IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')),
  
  -- Lifecycle tracking
  status text NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING', 'SENT', 'DELIVERED', 'OPENED', 'RESPONDED', 'EXPIRED', 'CANCELLED')),
  
  -- Magic link token for no-auth response
  token_hash text UNIQUE,               -- SHA256 of JWT token
  token_expires_at timestamptz,
  
  -- Timestamps
  created_at timestamptz DEFAULT now(),
  scheduled_send_at timestamptz,        -- When to send (business hours)
  sent_at timestamptz,
  delivered_at timestamptz,             -- Email/Slack delivery confirmed
  opened_at timestamptz,                -- Link clicked / email opened
  responded_at timestamptz,
  expires_at timestamptz,               -- When this alert expires (usually deadline)
  
  -- Response timeout for escalation
  escalation_timeout_at timestamptz,    -- If no response by this time, escalate
  
  -- Parent alert (for escalation chain)
  parent_alert_id uuid REFERENCES alerts(id),
  
  -- Notification details
  notification_channel text,            -- 'EMAIL', 'SLACK', 'BOTH'
  notification_metadata jsonb,          -- Email ID, Slack message ID, etc.
  
  -- Error tracking
  last_error text,
  retry_count int DEFAULT 0,
  max_retries int DEFAULT 3
);

-- Indexes for alert queries
CREATE INDEX IF NOT EXISTS idx_alerts_work_item ON alerts(work_item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_recipient ON alerts(actual_recipient_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, scheduled_send_at);
CREATE INDEX IF NOT EXISTS idx_alerts_pending ON alerts(status, escalation_timeout_at) 
  WHERE status IN ('SENT', 'DELIVERED', 'OPENED');
CREATE INDEX IF NOT EXISTS idx_alerts_token ON alerts(token_hash) WHERE token_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_alerts_deadline ON alerts(deadline_date, status);


-- ==========================================
-- STEP 4: WorkItemResponse Entity
-- ==========================================
-- Captures human input with full audit trail and versioning

CREATE TABLE IF NOT EXISTS work_item_responses (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- Link to alert (optional - can be unsolicited response)
  alert_id uuid REFERENCES alerts(id),
  work_item_id uuid NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
  
  -- Who responded
  responder_resource_id uuid NOT NULL REFERENCES resources(id),
  
  -- Response content
  reported_status text NOT NULL
    CHECK (reported_status IN ('ON_TRACK', 'DELAYED', 'BLOCKED', 'COMPLETED', 'CANCELLED')),
  
  -- Delay details (when reported_status = 'DELAYED')
  proposed_new_date date,
  delay_days int,                       -- Calculated: proposed_new_date - original_deadline
  
  -- Reason categorization (critical for analytics and duration recalculation)
  reason_category text
    CHECK (reason_category IN (
      'SCOPE_INCREASE',        -- More work discovered
      'STARTED_LATE',          -- Couldn't begin on time
      'RESOURCE_PULLED',       -- Team member reassigned
      'TECHNICAL_BLOCKER',     -- Technical complexity/bug
      'EXTERNAL_DEPENDENCY',   -- Waiting on external party
      'SPECIFICATION_CHANGE',  -- Requirements changed
      'QUALITY_ISSUE',         -- Rework needed
      'OTHER'
    )),
  
  -- Conditional details based on reason
  reason_details jsonb,                 -- Structured details per reason type
  /*
    For SCOPE_INCREASE: {"additional_work_percent": 25, "new_requirements": "..."}
    For RESOURCE_PULLED: {"available_effort_percent": 50, "until_date": "..."}
    For EXTERNAL_DEPENDENCY: {"waiting_for": "...", "expected_date": "..."}
    For TECHNICAL_BLOCKER: {"blocker_description": "...", "needs_help_from": "..."}
  */
  
  -- Free text comment
  comment text,
  
  -- Versioning (allows updates until deadline)
  response_version int DEFAULT 1,
  supersedes_response_id uuid REFERENCES work_item_responses(id),
  is_latest boolean DEFAULT true,
  
  -- Processing status
  processed boolean DEFAULT false,
  processed_at timestamptz,
  processed_by text,                    -- 'system:auto' or 'user:pm@email.com'
  
  -- Approval workflow (for delays)
  requires_approval boolean DEFAULT false,
  approval_status text DEFAULT 'PENDING'
    CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'AUTO_APPROVED')),
  approved_by_resource_id uuid REFERENCES resources(id),
  approved_at timestamptz,
  rejection_reason text,
  
  -- Impact analysis (calculated when response is received)
  impact_analysis jsonb,
  /*
    {
      "direct_delay_days": 2,
      "cascade_affected_items": ["TASK-004", "TASK-005"],
      "milestone_impact": {"name": "Beta Release", "new_date": "2025-04-25", "slip_days": 2},
      "resource_impact": {"over_allocated": ["RES-002"], "conflicts": [...]},
      "critical_path_affected": true
    }
  */
  
  -- Timestamps
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  
  -- Token validation (which magic link was used)
  token_used text,
  
  -- IP and user agent for security audit
  client_ip text,
  user_agent text
);

-- Indexes for response queries
CREATE INDEX IF NOT EXISTS idx_responses_work_item ON work_item_responses(work_item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_responses_alert ON work_item_responses(alert_id);
CREATE INDEX IF NOT EXISTS idx_responses_latest ON work_item_responses(work_item_id, is_latest) WHERE is_latest = true;
CREATE INDEX IF NOT EXISTS idx_responses_pending_approval ON work_item_responses(approval_status) 
  WHERE requires_approval = true AND approval_status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_responses_unprocessed ON work_item_responses(processed) WHERE processed = false;

-- Trigger to mark previous responses as not latest
CREATE OR REPLACE FUNCTION mark_previous_responses_not_latest()
RETURNS TRIGGER AS $$
BEGIN
  -- Mark all previous responses for this work item as not latest
  UPDATE work_item_responses
  SET is_latest = false, updated_at = now()
  WHERE work_item_id = NEW.work_item_id
  AND id != NEW.id
  AND is_latest = true;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS response_versioning_trigger ON work_item_responses;
CREATE TRIGGER response_versioning_trigger
AFTER INSERT ON work_item_responses
FOR EACH ROW
EXECUTE FUNCTION mark_previous_responses_not_latest();


-- ==========================================
-- STEP 5: Escalation Policy Configuration
-- ==========================================
-- Configurable escalation rules per program/organization

CREATE TABLE IF NOT EXISTS escalation_policies (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- Scope (program-specific or global)
  program_id uuid REFERENCES programs(id),  -- NULL = global default
  
  -- Policy name and description
  name text NOT NULL,
  description text,
  is_active boolean DEFAULT true,
  
  -- Alert timing
  days_before_deadline int DEFAULT 1,       -- Business days before deadline
  alert_time_of_day time DEFAULT '09:00',   -- When to send (local time)
  respect_business_hours boolean DEFAULT true,
  
  -- Escalation chain configuration
  escalation_chain jsonb NOT NULL DEFAULT '[
    {"level": 0, "target": "PRIMARY", "timeout_hours": 4},
    {"level": 1, "target": "BACKUP", "timeout_hours": 4},
    {"level": 2, "target": "MANAGER", "timeout_hours": 2},
    {"level": 3, "target": "PM", "timeout_hours": null}
  ]'::jsonb,
  
  -- Auto-approval rules
  auto_approve_delay_up_to_days int DEFAULT 0,  -- 0 = always require approval
  
  -- Notification settings
  send_reminders boolean DEFAULT true,
  reminder_interval_hours int DEFAULT 2,
  max_reminders int DEFAULT 3,
  
  -- Blockers get special treatment
  blocker_immediate_escalation boolean DEFAULT true,
  blocker_notify_pm_always boolean DEFAULT true,
  
  -- Metadata
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  created_by text
);

-- Insert default global policy
INSERT INTO escalation_policies (name, description, program_id) VALUES
  ('Default Escalation Policy', 'Standard escalation chain: Primary → Backup → Manager → PM', NULL)
ON CONFLICT DO NOTHING;


-- ==========================================
-- STEP 6: Magic Link Tokens Table
-- ==========================================
-- Secure token management for no-auth responses

CREATE TABLE IF NOT EXISTS response_tokens (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- Token identity
  token_hash text UNIQUE NOT NULL,      -- SHA256 of the actual token
  
  -- What this token authorizes
  work_item_id uuid NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
  resource_id uuid NOT NULL REFERENCES resources(id),  -- Who can use this token
  alert_id uuid REFERENCES alerts(id),
  
  -- Token lifecycle
  created_at timestamptz DEFAULT now(),
  expires_at timestamptz NOT NULL,
  
  -- Usage tracking
  is_used boolean DEFAULT false,        -- For one-time tokens (we use updateable)
  last_used_at timestamptz,
  use_count int DEFAULT 0,
  max_uses int,                         -- NULL = unlimited until expiry
  
  -- Revocation
  is_revoked boolean DEFAULT false,
  revoked_at timestamptz,
  revoked_by text,
  revocation_reason text,
  
  -- Security
  created_from_ip text,
  allowed_actions text[] DEFAULT ARRAY['respond']
);

CREATE INDEX IF NOT EXISTS idx_response_tokens_hash ON response_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_response_tokens_work_item ON response_tokens(work_item_id);
CREATE INDEX IF NOT EXISTS idx_response_tokens_active ON response_tokens(expires_at, is_revoked) 
  WHERE is_revoked = false;


-- ==========================================
-- STEP 7: Alert Queue Table (for async processing)
-- ==========================================
-- Queue for scheduled and retry alerts

CREATE TABLE IF NOT EXISTS alert_queue (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- What to process
  alert_id uuid REFERENCES alerts(id) ON DELETE CASCADE,
  action text NOT NULL
    CHECK (action IN ('SEND', 'ESCALATE', 'REMIND', 'EXPIRE', 'PROCESS_RESPONSE')),
  
  -- Scheduling
  scheduled_for timestamptz NOT NULL,
  priority int DEFAULT 5,               -- 1=highest, 10=lowest
  
  -- Processing status
  status text DEFAULT 'PENDING'
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')),
  
  -- Retry logic
  attempts int DEFAULT 0,
  max_attempts int DEFAULT 3,
  last_attempt_at timestamptz,
  last_error text,
  next_retry_at timestamptz,
  
  -- Context
  payload jsonb,                        -- Additional data for processing
  
  -- Timestamps
  created_at timestamptz DEFAULT now(),
  processed_at timestamptz,
  
  -- Idempotency key (prevent duplicate processing)
  idempotency_key text UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_alert_queue_pending ON alert_queue(scheduled_for, priority) 
  WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_alert_queue_retry ON alert_queue(next_retry_at) 
  WHERE status = 'FAILED' AND attempts < max_attempts;


-- ==========================================
-- STEP 8: Business Day Functions
-- ==========================================

-- Function to check if a date is a business day
CREATE OR REPLACE FUNCTION is_business_day(
  check_date date,
  country text DEFAULT 'US'
)
RETURNS boolean AS $$
DECLARE
  day_of_week int;
  is_holiday boolean;
BEGIN
  -- Check if weekend (0=Sunday, 6=Saturday in PostgreSQL)
  day_of_week := EXTRACT(DOW FROM check_date);
  IF day_of_week IN (0, 6) THEN
    RETURN false;
  END IF;
  
  -- Check if holiday
  SELECT EXISTS(
    SELECT 1 FROM holiday_calendar
    WHERE holiday_date = check_date
    AND (country_code = country OR country_code IS NULL)
  ) INTO is_holiday;
  
  RETURN NOT is_holiday;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to get N business days before a date
CREATE OR REPLACE FUNCTION business_days_before(
  target_date date,
  num_days int,
  country text DEFAULT 'US'
)
RETURNS date AS $$
DECLARE
  result_date date;
  days_counted int := 0;
BEGIN
  result_date := target_date;
  
  WHILE days_counted < num_days LOOP
    result_date := result_date - interval '1 day';
    
    IF is_business_day(result_date, country) THEN
      days_counted := days_counted + 1;
    END IF;
    
    -- Safety: don't go back more than 30 calendar days for 1 business day
    IF result_date < target_date - interval '30 days' THEN
      RETURN result_date;
    END IF;
  END LOOP;
  
  RETURN result_date;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to get next business day at specific time
CREATE OR REPLACE FUNCTION next_business_day_at_time(
  from_timestamp timestamptz,
  target_time time,
  resource_timezone text DEFAULT 'UTC'
)
RETURNS timestamptz AS $$
DECLARE
  result_date date;
  result_timestamp timestamptz;
BEGIN
  -- Start from tomorrow if it's already past target time today
  result_date := (from_timestamp AT TIME ZONE resource_timezone)::date;
  
  IF (from_timestamp AT TIME ZONE resource_timezone)::time > target_time THEN
    result_date := result_date + interval '1 day';
  END IF;
  
  -- Find next business day
  WHILE NOT is_business_day(result_date, 'US') LOOP
    result_date := result_date + interval '1 day';
  END LOOP;
  
  -- Combine date and time in resource timezone, then convert to UTC
  result_timestamp := (result_date || ' ' || target_time)::timestamp AT TIME ZONE resource_timezone;
  
  RETURN result_timestamp;
END;
$$ LANGUAGE plpgsql STABLE;


-- ==========================================
-- STEP 9: Escalation Chain Resolution Function
-- ==========================================

-- Function to get the escalation chain for a resource
CREATE OR REPLACE FUNCTION get_escalation_chain(
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
  v_policy_id uuid;
  v_chain jsonb;
  v_resource record;
  v_backup_id uuid;
  v_manager_id uuid;
  v_pm_id uuid;
BEGIN
  -- Get applicable escalation policy
  SELECT id, escalation_chain INTO v_policy_id, v_chain
  FROM escalation_policies
  WHERE (program_id = p_program_id OR program_id IS NULL)
  AND is_active = true
  ORDER BY program_id NULLS LAST  -- Program-specific takes precedence
  LIMIT 1;
  
  -- Get resource info
  SELECT * INTO v_resource FROM resources WHERE id = p_resource_id;
  
  -- Level 0: Primary resource
  RETURN QUERY
  SELECT 
    0 AS escalation_level,
    'PRIMARY'::text AS target_type,
    v_resource.id AS target_resource_id,
    v_resource.name AS target_resource_name,
    COALESCE(v_resource.notification_email, v_resource.email) AS target_email,
    v_resource.availability_status = 'ACTIVE' AS is_available,
    v_resource.availability_status;
  
  -- Level 1: Backup resource
  IF v_resource.backup_resource_id IS NOT NULL THEN
    RETURN QUERY
    SELECT 
      1 AS escalation_level,
      'BACKUP'::text AS target_type,
      r.id AS target_resource_id,
      r.name AS target_resource_name,
      COALESCE(r.notification_email, r.email) AS target_email,
      r.availability_status = 'ACTIVE' AS is_available,
      r.availability_status
    FROM resources r
    WHERE r.id = v_resource.backup_resource_id;
  END IF;
  
  -- Level 2: Manager
  IF v_resource.manager_id IS NOT NULL THEN
    RETURN QUERY
    SELECT 
      2 AS escalation_level,
      'MANAGER'::text AS target_type,
      r.id AS target_resource_id,
      r.name AS target_resource_name,
      COALESCE(r.notification_email, r.email) AS target_email,
      r.availability_status = 'ACTIVE' AS is_available,
      r.availability_status
    FROM resources r
    WHERE r.id = v_resource.manager_id;
  END IF;
  
  -- Level 3: PM (from program, if available)
  -- TODO: Add PM lookup from program table when we add that field
  
  RETURN;
END;
$$ LANGUAGE plpgsql STABLE;


-- ==========================================
-- STEP 10: Find Next Available Escalation Target
-- ==========================================

CREATE OR REPLACE FUNCTION find_available_escalation_target(
  p_resource_id uuid,
  p_program_id uuid DEFAULT NULL,
  p_start_level int DEFAULT 0
)
RETURNS TABLE (
  target_resource_id uuid,
  target_resource_name text,
  target_email text,
  escalation_level int,
  target_type text,
  skip_reason text
) AS $$
BEGIN
  RETURN QUERY
  WITH chain AS (
    SELECT * FROM get_escalation_chain(p_resource_id, p_program_id)
    WHERE ec.escalation_level >= p_start_level
  )
  SELECT 
    c.target_resource_id,
    c.target_resource_name,
    c.target_email,
    c.escalation_level,
    c.target_type,
    CASE 
      WHEN NOT c.is_available THEN 'Resource ' || c.availability_status
      ELSE NULL
    END AS skip_reason
  FROM chain c
  WHERE c.is_available = true
  ORDER BY c.escalation_level
  LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;


-- ==========================================
-- STEP 11: Impact Analysis Function
-- ==========================================

-- Function to calculate impact of a delay
CREATE OR REPLACE FUNCTION calculate_delay_impact(
  p_work_item_id uuid,
  p_new_end_date date,
  p_reason_category text DEFAULT NULL
)
RETURNS jsonb AS $$
DECLARE
  v_work_item record;
  v_original_end date;
  v_delay_days int;
  v_program_id uuid;
  v_affected_items jsonb;
  v_milestone_impact jsonb;
  v_resource_conflicts jsonb;
  v_is_critical_path boolean;
BEGIN
  -- Get work item details
  SELECT 
    wi.*,
    pj.program_id
  INTO v_work_item
  FROM work_items wi
  JOIN phases ph ON wi.phase_id = ph.id
  JOIN projects pj ON ph.project_id = pj.id
  WHERE wi.id = p_work_item_id;
  
  IF v_work_item IS NULL THEN
    RETURN jsonb_build_object('error', 'Work item not found');
  END IF;
  
  v_original_end := v_work_item.current_end;
  v_delay_days := p_new_end_date - v_original_end;
  v_program_id := v_work_item.program_id;
  v_is_critical_path := v_work_item.is_critical_path;
  
  -- Find all downstream affected items (successors)
  WITH RECURSIVE downstream AS (
    -- Direct successors
    SELECT 
      wi.id,
      wi.external_id,
      wi.name,
      wi.current_start,
      wi.current_end,
      1 as depth
    FROM dependencies d
    JOIN work_items wi ON d.successor_item_id = wi.id
    WHERE d.predecessor_item_id = p_work_item_id
    AND wi.status NOT IN ('Cancelled', 'Completed')
    
    UNION ALL
    
    -- Indirect successors
    SELECT 
      wi.id,
      wi.external_id,
      wi.name,
      wi.current_start,
      wi.current_end,
      ds.depth + 1
    FROM downstream ds
    JOIN dependencies d ON d.predecessor_item_id = ds.id
    JOIN work_items wi ON d.successor_item_id = wi.id
    WHERE wi.status NOT IN ('Cancelled', 'Completed')
    AND ds.depth < 10
  )
  SELECT jsonb_agg(jsonb_build_object(
    'id', id,
    'external_id', external_id,
    'name', name,
    'current_start', current_start,
    'current_end', current_end,
    'new_start', current_start + (v_delay_days || ' days')::interval,
    'new_end', current_end + (v_delay_days || ' days')::interval,
    'depth', depth
  ))
  INTO v_affected_items
  FROM downstream;
  
  -- Build impact analysis result
  RETURN jsonb_build_object(
    'work_item_id', p_work_item_id,
    'original_end_date', v_original_end,
    'proposed_end_date', p_new_end_date,
    'delay_days', v_delay_days,
    'reason_category', p_reason_category,
    'is_critical_path', v_is_critical_path,
    'cascade_affected_items', COALESCE(v_affected_items, '[]'::jsonb),
    'cascade_count', COALESCE(jsonb_array_length(v_affected_items), 0),
    'analysis_timestamp', now()
  );
END;
$$ LANGUAGE plpgsql;


-- ==========================================
-- STEP 12: Response Processing Trigger
-- ==========================================

-- When a response is approved, update the work item
CREATE OR REPLACE FUNCTION process_approved_response()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.approval_status = 'APPROVED' AND OLD.approval_status != 'APPROVED' THEN
    -- Update work item dates based on response
    IF NEW.reported_status = 'DELAYED' AND NEW.proposed_new_date IS NOT NULL THEN
      UPDATE work_items
      SET 
        current_end = NEW.proposed_new_date,
        updated_at = now()
      WHERE id = NEW.work_item_id;
      
      -- Log to audit trail
      INSERT INTO audit_logs (
        entity_type, entity_id, action, field_changed,
        old_value, new_value, change_source, changed_by, reason
      )
      SELECT
        'work_item', NEW.work_item_id, 'updated', 'current_end',
        wi.current_end::text, NEW.proposed_new_date::text,
        'status_response', NEW.approved_by_resource_id::text,
        NEW.reason_category || ': ' || COALESCE(NEW.comment, '')
      FROM work_items wi WHERE wi.id = NEW.work_item_id;
    END IF;
    
    -- Mark response as processed
    NEW.processed := true;
    NEW.processed_at := now();
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS process_response_approval_trigger ON work_item_responses;
CREATE TRIGGER process_response_approval_trigger
BEFORE UPDATE OF approval_status ON work_item_responses
FOR EACH ROW
EXECUTE FUNCTION process_approved_response();


-- ==========================================
-- STEP 13: View for Pending Status Checks
-- ==========================================

CREATE OR REPLACE VIEW pending_status_checks AS
SELECT 
  wi.id AS work_item_id,
  wi.external_id,
  wi.name AS work_item_name,
  wi.current_end AS deadline_date,
  r.id AS resource_id,
  r.name AS resource_name,
  r.email AS resource_email,
  r.availability_status,
  r.backup_resource_id,
  r.manager_id,
  pj.program_id,
  prog.name AS program_name,
  wi.is_critical_path,
  wi.status AS work_item_status,
  -- Check if alert already sent (get most recent by created_at)
  (SELECT a.id FROM alerts a 
   WHERE a.work_item_id = wi.id 
   AND a.deadline_date = wi.current_end
   AND a.status NOT IN ('EXPIRED', 'CANCELLED')
   ORDER BY a.created_at DESC
   LIMIT 1) AS existing_alert_id,
  -- Check latest response
  (SELECT wir.reported_status FROM work_item_responses wir 
   WHERE wir.work_item_id = wi.id 
   AND wir.is_latest = true
   LIMIT 1) AS latest_response_status
FROM work_items wi
JOIN resources r ON wi.resource_id = r.id
JOIN phases ph ON wi.phase_id = ph.id
JOIN projects pj ON ph.project_id = pj.id
JOIN programs prog ON pj.program_id = prog.id
WHERE wi.status NOT IN ('Cancelled', 'Completed')
AND wi.actual_end IS NULL  -- Not actually completed
AND wi.current_end >= CURRENT_DATE;  -- Deadline is today or future


-- ==========================================
-- STEP 14: Permissions
-- ==========================================

GRANT ALL ON holiday_calendar TO authenticated;
GRANT ALL ON alerts TO authenticated;
GRANT ALL ON work_item_responses TO authenticated;
GRANT ALL ON escalation_policies TO authenticated;
GRANT ALL ON response_tokens TO authenticated;
GRANT ALL ON alert_queue TO authenticated;
GRANT SELECT ON pending_status_checks TO authenticated;


-- ==========================================
-- MIGRATION COMPLETE
-- ==========================================
-- 
-- To verify:
-- SELECT * FROM get_escalation_chain('resource-uuid-here');
-- SELECT business_days_before('2025-04-15', 1);
-- SELECT is_business_day('2025-12-25');
-- SELECT * FROM pending_status_checks;
--
