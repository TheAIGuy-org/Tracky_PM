/**
 * TypeScript type definitions for Tracky PM
 * Mirrors backend Pydantic schemas exactly for type safety
 */

// ==========================================
// ENUMS - Match PostgreSQL ENUM types
// ==========================================

export type DependencyType = 'FS' | 'SS' | 'FF' | 'SF';

export type WorkStatus = 
  | 'Not Started' 
  | 'In Progress' 
  | 'Completed' 
  | 'On Hold' 
  | 'Cancelled';

export type ProgramStatus = 
  | 'Planned' 
  | 'Active' 
  | 'Completed' 
  | 'Cancelled';

export type ComplexityLevel = 'Low' | 'Medium' | 'High';

export type StrategicImportance = 'Low' | 'Medium' | 'High';

export type CustomerImpact = 'Low' | 'Medium' | 'High';

// ==========================================
// BASE INTERFACES
// ==========================================

export interface TimestampMixin {
  created_at?: string;
}

export interface ExternalIdMixin {
  external_id: string;
}

// ==========================================
// RESOURCE
// ==========================================

export interface Resource extends ExternalIdMixin, TimestampMixin {
  id: string;
  name: string;
  email: string;
  role?: string;
  home_team?: string;
  cost_per_hour?: number;
  max_utilization: number;
  skill_level?: string;
  location?: string;
  availability_status: string;
}

export interface ResourceUtilization extends Resource {
  total_allocation: number;
  utilization_status: 'Available' | 'At-Risk' | 'Over-Allocated';
  active_tasks: number;
  // UI display fields
  resource_id: string;
  utilization_percent?: number;
  assigned_tasks?: number;
  total_hours?: number;
  available_hours?: number;
}

// ==========================================
// PROGRAM
// ==========================================

export interface Program extends ExternalIdMixin, TimestampMixin {
  id: string;
  name: string;
  description?: string;
  status: ProgramStatus;
  baseline_start_date: string;
  baseline_end_date: string;
  program_owner?: string;
  priority?: number;
  budget?: number;
  strategic_goal?: string;
  noise_threshold_days: number;
}

// ==========================================
// PROJECT
// ==========================================

export interface Project extends ExternalIdMixin {
  id: string;
  program_id: string;
  name: string;
}

// ==========================================
// PHASE
// ==========================================

export interface Phase extends ExternalIdMixin {
  id: string;
  project_id: string;
  name: string;
  sequence: number;
  phase_type?: string;
}

// ==========================================
// WORK ITEM - THE CORE ENTITY
// ==========================================

export interface WorkItem extends ExternalIdMixin, TimestampMixin {
  id: string;
  phase_id: string;
  resource_id?: string;
  name: string;
  
  // Timeline - Plan/Baseline
  planned_start: string;
  planned_end: string;
  planned_effort_hours?: number;
  allocation_percent: number;
  
  // Timeline - Reality (Current/Actual)
  current_start: string;
  current_end: string;
  actual_start?: string;
  actual_end?: string;
  
  // Status
  status: WorkStatus;
  completion_percent: number;
  slack_days: number;
  
  // Risk & Metadata
  complexity?: ComplexityLevel | string;
  revenue_impact?: number;
  strategic_importance?: StrategicImportance;
  customer_impact?: CustomerImpact;
  is_critical_launch: boolean;
  feature_name?: string;
  
  // Flags
  flag_for_review?: boolean;
  review_message?: string;
  
  updated_at?: string;

  // UI-friendly aliases (optional - populated from enriched data)
  task_code?: string; // Alias for external_id
  wbs?: string;
  progress?: number; // Alias for completion_percent
  priority?: string;
  assigned_resources?: string[];
  program?: string;
  project?: string;
  phase?: string;
}

// Enriched work item with joined data for display
export interface WorkItemEnriched extends WorkItem {
  resource_name?: string;
  resource_email?: string;
  phase_name?: string;
  project_name?: string;
  program_name?: string;
  program_id?: string;
  project_id?: string;
  
  // Computed
  is_delayed: boolean;
  days_delayed: number;
  is_on_critical_path: boolean;
}

// ==========================================
// DEPENDENCY
// ==========================================

export interface Dependency {
  id: string;
  successor_item_id: string;
  predecessor_item_id: string;
  dependency_type: DependencyType;
  lag_days: number;
  notes?: string;
}

export interface DependencyEnriched extends Dependency {
  successor_name?: string;
  predecessor_name?: string;
  successor_external_id?: string;
  predecessor_external_id?: string;
}

// ==========================================
// IMPORT RESPONSE
// ==========================================

export interface ImportSummary {
  tasks_created: number;
  tasks_updated: number;
  tasks_preserved: number;
  tasks_cancelled: number;
  tasks_flagged: number;
  
  resources_synced: number;
  programs_synced: number;
  projects_synced: number;
  phases_synced: number;
  dependencies_synced: number;
  
  work_items_parsed: number;
  resources_parsed: number;
  dependencies_parsed: number;
  
  recalculation_time_ms: number;
  critical_path_items: number;
}

export interface ImportWarning {
  type: 'validation' | 'resource' | 'dependency' | 'recalculation';
  row?: number;
  field?: string;
  message: string;
}

export interface ImportError {
  row?: number;
  field?: string;
  value?: string;
  message: string;
}

export interface FlaggedItem {
  id: string;
  external_id: string;
  name?: string;
  status?: WorkStatus;
  completion_percent?: number;
  review_message?: string;
}

export interface ImportResponse {
  status: 'success' | 'partial_success' | 'validation_failed' | 'failed' | 'pending';
  summary: ImportSummary;
  warnings: ImportWarning[];
  errors: ImportError[];
  flagged_items: FlaggedItem[];
  baseline_version_id?: string;
  import_batch_id?: string;
  execution_time_ms: number;
}

// ==========================================
// VALIDATION RESPONSE (Pre-import)
// ==========================================

export interface ValidationResult {
  is_valid: boolean;
  errors: ImportError[];
  warnings: ImportWarning[];
}

export interface ValidateResponse {
  valid: boolean;
  summary: {
    work_items: number;
    resources: number;
    dependencies: number;
    programs: number;
  };
  validation: ValidationResult;
}

// ==========================================
// IMPORT BATCH (Audit Trail)
// ==========================================

export interface ImportBatch {
  id: string;
  program_id?: string;
  file_name: string;
  file_hash: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
  items_processed: number;
  items_created: number;
  items_updated: number;
  items_cancelled: number;
  items_flagged: number;
  error_message?: string;
}

// ==========================================
// BASELINE VERSION (Scope Tracking)
// ==========================================

export interface BaselineVersion {
  id: string;
  program_id: string;
  version_number: number;
  import_batch_id?: string;
  snapshot_date: string;
  created_by?: string;
  notes?: string;
  work_item_count: number;
  total_effort_hours: number;
  total_duration_days: number;
  created_at: string;
}

// ==========================================
// AUDIT LOG
// ==========================================

export interface AuditLog {
  id: string;
  entity_type: 'work_item' | 'resource' | 'program' | 'project' | 'phase' | 'dependency';
  entity_id: string;
  action: 'created' | 'updated' | 'deleted' | 'cancelled' | 'resolved' | string;
  field_changed?: string;
  old_value?: string;
  new_value?: string;
  change_source: 'excel_import' | 'recalculation' | 'manual';
  import_batch_id?: string;
  changed_by?: string;
  changed_at: string;
  reason?: string;
  
  // UI convenience aliases
  timestamp?: string; // Alias for changed_at
  user?: string; // Alias for changed_by
  batch_id?: string; // Alias for import_batch_id
  details?: string; // Constructed from field_changed/old_value/new_value
  affected_items?: number;
  source_file?: string;
  metadata?: Record<string, unknown>;
}

// ==========================================
// API RESPONSE WRAPPERS
// ==========================================

export interface ListResponse<T> {
  data: T[];
  count: number;
}

export interface BatchListResponse {
  batches: ImportBatch[];
  count: number;
}

export interface BatchDetailResponse {
  batch: ImportBatch;
  audit_logs: AuditLog[];
  audit_count: number;
}

export interface FlaggedItemsResponse {
  flagged_count: number;
  items: FlaggedItem[];
}

export interface ResourceUtilizationResponse {
  total_resources: number;
  over_allocated_count: number;
  at_risk_count: number;
  over_allocated: ResourceUtilization[];
  at_risk: ResourceUtilization[];
  all_resources: ResourceUtilization[];
}

export interface BaselineVersionsResponse {
  program_id: string;
  version_count: number;
  versions: BaselineVersion[];
}

// ==========================================
// HEALTH CHECK
// ==========================================

export interface HealthCheckResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  service?: string;
  version?: string;
  debug?: boolean;
}

// ==========================================
// PROACTIVE TRACKING - ALERTS & RESPONSES
// ==========================================

export type AlertStatus = 'PENDING' | 'SENT' | 'DELIVERED' | 'OPENED' | 'RESPONDED' | 'EXPIRED' | 'CANCELLED';
export type AlertType = 'STATUS_CHECK' | 'ESCALATION' | 'BLOCKER_REPORT' | 'APPROVAL_REQUEST' | 'NOTIFICATION';
export type AlertUrgency = 'LOW' | 'NORMAL' | 'HIGH' | 'CRITICAL';

export type ReportedStatus = 'ON_TRACK' | 'DELAYED' | 'BLOCKED' | 'COMPLETED' | 'CANCELLED';
export type ReasonCategory = 
  | 'SCOPE_INCREASE' 
  | 'STARTED_LATE' 
  | 'RESOURCE_PULLED' 
  | 'TECHNICAL_BLOCKER' 
  | 'EXTERNAL_DEPENDENCY' 
  | 'SPECIFICATION_CHANGE' 
  | 'QUALITY_ISSUE' 
  | 'OTHER';

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'AUTO_APPROVED';

export interface Alert {
  id: string;
  work_item_id: string;
  deadline_date: string;
  intended_recipient_id: string;
  actual_recipient_id?: string;
  escalation_reason?: string;
  alert_type: AlertType;
  escalation_level: number;
  urgency: AlertUrgency;
  status: AlertStatus;
  token_expires_at?: string;
  created_at: string;
  scheduled_send_at?: string;
  sent_at?: string;
  delivered_at?: string;
  opened_at?: string;
  responded_at?: string;
  expires_at?: string;
  escalation_timeout_at?: string;
  parent_alert_id?: string;
  notification_channel?: string;
  last_error?: string;
  retry_count: number;
  
  // Enriched fields (joined data)
  work_item_name?: string;
  work_item_external_id?: string;
  intended_recipient_name?: string;
  actual_recipient_name?: string;
  program_name?: string;
}

export interface ReasonDetails {
  // SCOPE_INCREASE
  additional_work_percent?: number;
  new_requirements?: string;
  
  // RESOURCE_PULLED
  available_effort_percent?: number;
  until_date?: string;
  
  // EXTERNAL_DEPENDENCY
  waiting_for?: string;
  expected_date?: string;
  
  // TECHNICAL_BLOCKER
  blocker_description?: string;
  needs_help_from?: string;
}

export interface WorkItemResponse {
  id: string;
  alert_id?: string;
  work_item_id: string;
  responder_resource_id: string;
  reported_status: ReportedStatus;
  proposed_new_date?: string;
  delay_days?: number;
  reason_category?: ReasonCategory;
  reason_details?: ReasonDetails;
  comment?: string;
  response_version: number;
  supersedes_response_id?: string;
  is_latest: boolean;
  processed: boolean;
  processed_at?: string;
  requires_approval: boolean;
  approval_status: ApprovalStatus;
  approved_by_resource_id?: string;
  approved_at?: string;
  rejection_reason?: string;
  impact_analysis?: ImpactAnalysis;
  created_at: string;
  updated_at: string;
  
  // Enriched fields
  responder_name?: string;
  work_item_name?: string;
  work_item_external_id?: string;
  approved_by_name?: string;
}

export interface ImpactAnalysis {
  direct_delay_days: number;
  cascade_affected_items: string[];
  milestone_impact?: {
    name: string;
    new_date: string;
    slip_days: number;
  };
  resource_impact?: {
    over_allocated: string[];
    conflicts: Array<{
      resource_id: string;
      conflict_date: string;
      items: string[];
    }>;
  };
  critical_path_affected: boolean;
}

// Alert response submission (what gets POSTed)
export interface AlertResponseSubmission {
  reported_status: ReportedStatus;
  proposed_new_date?: string;
  reason_category?: ReasonCategory;
  reason_details?: ReasonDetails;
  comment?: string;
}

// Token validation response
export interface TokenValidation {
  valid: boolean;
  alert_id: string;
  work_item_id: string;
  work_item: {
    id: string;
    external_id: string;
    name: string;
    planned_end: string;
    current_end: string;
    status: WorkStatus;
    completion_percent: number;
    phase_name?: string;
    project_name?: string;
    program_name?: string;
  };
  responder: {
    id: string;
    name: string;
    email: string;
  };
  deadline: string;
  can_update: boolean;
  previous_response?: WorkItemResponse;
  error?: string;
}

// Alerts list response
export interface AlertsListResponse {
  alerts: Alert[];
  count: number;
  pending_count: number;
  responded_count: number;
}

// Pending approvals response
export interface PendingApprovalsResponse {
  approvals: WorkItemResponse[];
  count: number;
}

// Due tomorrow response
export interface DueTomorrowResponse {
  date: string;
  items: Array<{
    work_item_id: string;
    work_item_external_id: string;
    work_item_name: string;
    deadline: string;
    resource_id: string;
    resource_name: string;
    resource_email: string;
    alert_exists: boolean;
    existing_alert_status?: AlertStatus;
  }>;
  count: number;
}

