/**
 * Alert Response Page - Magic Link Landing Page
 * 
 * This is the page workers land on when clicking a magic link.
 * No authentication required - the JWT token in the URL provides authorization.
 * 
 * Features:
 * - Shows work item context
 * - Captures status (ON_TRACK, DELAYED, BLOCKED, etc.)
 * - Conditional questions based on status
 * - Reason categorization for delays
 * - Impact preview before submission
 */
import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  CheckCircle2,
  Clock,
  Calendar,
  User,
  FileText,
  Send,
  Loader2,
  XCircle,
  Info,
  AlertTriangle,
  TrendingUp,
} from 'lucide-react';
import { api } from '../lib/api';
import { getTodayDateString, isDateInPast, isDateInFuture } from '../lib/utils';
import type { ImpactAnalysis } from '../lib/api';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import type {
  TokenValidation,
  ReportedStatus,
  ReasonCategory,
  AlertResponseSubmission,
  ReasonDetails,
  WorkItemResponse,
} from '../types';

// Status options with metadata
const STATUS_OPTIONS: Array<{
  value: ReportedStatus;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}> = [
  {
    value: 'ON_TRACK',
    label: 'On Track',
    description: 'Will complete by the deadline',
    icon: CheckCircle2,
    color: 'text-green-600 bg-green-50 border-green-200 hover:bg-green-100',
  },
  {
    value: 'COMPLETED',
    label: 'Already Completed',
    description: 'Task is already finished',
    icon: CheckCircle2,
    color: 'text-blue-600 bg-blue-50 border-blue-200 hover:bg-blue-100',
  },
  {
    value: 'DELAYED',
    label: 'Will Be Delayed',
    description: 'Need more time to complete',
    icon: Clock,
    color: 'text-amber-600 bg-amber-50 border-amber-200 hover:bg-amber-100',
  },
  {
    value: 'BLOCKED',
    label: 'Blocked',
    description: 'Cannot proceed due to blocker',
    icon: XCircle,
    color: 'text-red-600 bg-red-50 border-red-200 hover:bg-red-100',
  },
];

// Reason categories for delays
const REASON_CATEGORIES: Array<{
  value: ReasonCategory;
  label: string;
  description: string;
  fields: string[];
}> = [
  {
    value: 'SCOPE_INCREASE',
    label: 'Scope Increased',
    description: 'More work discovered than originally planned',
    fields: ['additional_work_percent', 'new_requirements'],
  },
  {
    value: 'STARTED_LATE',
    label: 'Started Late',
    description: "Couldn't begin on the planned start date",
    fields: [],
  },
  {
    value: 'RESOURCE_PULLED',
    label: 'Resource Pulled',
    description: 'Team member reassigned to other work',
    fields: ['available_effort_percent', 'until_date'],
  },
  {
    value: 'TECHNICAL_BLOCKER',
    label: 'Technical Blocker',
    description: 'Technical complexity or bug blocking progress',
    fields: ['blocker_description', 'needs_help_from'],
  },
  {
    value: 'EXTERNAL_DEPENDENCY',
    label: 'External Dependency',
    description: 'Waiting on external party or team',
    fields: ['waiting_for', 'expected_date'],
  },
  {
    value: 'SPECIFICATION_CHANGE',
    label: 'Spec Change',
    description: 'Requirements changed mid-work',
    fields: [],
  },
  {
    value: 'QUALITY_ISSUE',
    label: 'Quality Issue',
    description: 'Rework needed due to quality concerns',
    fields: [],
  },
  {
    value: 'OTHER',
    label: 'Other',
    description: 'Other reason not listed above',
    fields: [],
  },
];

export function AlertResponsePage() {
  const { token } = useParams<{ token: string }>();
  
  // State
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<TokenValidation | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submittedResponse, setSubmittedResponse] = useState<WorkItemResponse | null>(null);
  
  // Form state
  const [selectedStatus, setSelectedStatus] = useState<ReportedStatus | null>(null);
  const [proposedDate, setProposedDate] = useState<string>('');
  const [reasonCategory, setReasonCategory] = useState<ReasonCategory | null>(null);
  const [reasonDetails, setReasonDetails] = useState<ReasonDetails>({});
  const [comment, setComment] = useState('');
  
  // Impact analysis state
  const [impactAnalysis, setImpactAnalysis] = useState<ImpactAnalysis | null>(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  
  // FIX: Date validation helpers (timezone-safe)
  const today = getTodayDateString(); // Uses timezone-safe utility
  const minProposedDate = validation?.deadline && validation.deadline > today 
    ? validation.deadline 
    : today; // Can't propose a date in the past
  
  // FIX: Idempotency key for duplicate prevention
  const [idempotencyKey] = useState(() => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  
  // FIX: Form validation
  const isFormValid = (): boolean => {
    if (!selectedStatus) return false;
    
    if (selectedStatus === 'DELAYED' || selectedStatus === 'BLOCKED') {
      // Must have a proposed date
      if (!proposedDate) return false;
      // Proposed date must be in the future (or at least today) - timezone-safe
      if (isDateInPast(proposedDate)) return false;
      // Must have a reason category
      if (!reasonCategory) return false;
    }
    
    return true;
  };

  // Fetch impact analysis when proposed date changes
  const fetchImpactAnalysis = useCallback(async () => {
    if (!validation?.work_item.id || !proposedDate) {
      setImpactAnalysis(null);
      return;
    }
    
    setLoadingImpact(true);
    try {
      const impact = await api.alerts.previewImpact(
        validation.work_item.id,
        proposedDate,
        reasonCategory || undefined
      );
      setImpactAnalysis(impact);
    } catch (err) {
      console.error('Failed to fetch impact analysis:', err);
      setImpactAnalysis(null);
    } finally {
      setLoadingImpact(false);
    }
  }, [validation?.work_item.id, proposedDate, reasonCategory]);

  // Debounce impact analysis fetch
  useEffect(() => {
    if ((selectedStatus === 'DELAYED' || selectedStatus === 'BLOCKED') && proposedDate) {
      const timer = setTimeout(fetchImpactAnalysis, 500);
      return () => clearTimeout(timer);
    } else {
      setImpactAnalysis(null);
    }
  }, [selectedStatus, proposedDate, fetchImpactAnalysis]);

  // Validate token on load
  useEffect(() => {
    if (!token) {
      setError('Invalid link - no token provided');
      setLoading(false);
      return;
    }

    api.alerts
      .validateToken(token)
      .then((result) => {
        if (!result.valid) {
          setError(result.error || 'This link is no longer valid');
        } else {
          setValidation(result);
          // Pre-fill from previous response if exists
          if (result.previous_response) {
            setSelectedStatus(result.previous_response.reported_status);
            if (result.previous_response.proposed_new_date) {
              setProposedDate(result.previous_response.proposed_new_date);
            }
            if (result.previous_response.reason_category) {
              setReasonCategory(result.previous_response.reason_category);
            }
            if (result.previous_response.reason_details) {
              setReasonDetails(result.previous_response.reason_details);
            }
            if (result.previous_response.comment) {
              setComment(result.previous_response.comment);
            }
          }
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to validate link');
        setLoading(false);
      });
  }, [token]);

  // Handle submission
  const handleSubmit = async () => {
    if (!token || !selectedStatus) return;
    
    // FIX: Client-side validation before submit
    if (!isFormValid()) {
      setError('Please fill in all required fields correctly');
      return;
    }
    
    // FIX: Validate proposed date is not in the past (using timezone-safe utility)
    if ((selectedStatus === 'DELAYED' || selectedStatus === 'BLOCKED') && proposedDate) {
      if (!isDateInFuture(proposedDate)) {
        setError('Proposed date must be a future date');
        return;
      }
    }

    setSubmitting(true);
    setError(null); // Clear previous errors
    
    try {
      const submission: AlertResponseSubmission = {
        reported_status: selectedStatus,
        comment: comment || undefined,
      };

      if (selectedStatus === 'DELAYED' || selectedStatus === 'BLOCKED') {
        submission.proposed_new_date = proposedDate || undefined;
        submission.reason_category = reasonCategory || undefined;
        submission.reason_details = Object.keys(reasonDetails).length > 0 ? reasonDetails : undefined;
      }

      // FIX: Pass idempotency key to prevent duplicate submissions
      const result = await api.alerts.submitResponse(token, submission, idempotencyKey);
      setSubmittedResponse(result.response);
      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || 'Failed to submit response');
    } finally {
      setSubmitting(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-blue-600 mx-auto" />
          <p className="mt-4 text-gray-600">Validating your link...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full p-8 text-center">
          <XCircle className="h-16 w-16 text-red-500 mx-auto" />
          <h1 className="mt-4 text-xl font-semibold text-gray-900">Link Invalid</h1>
          <p className="mt-2 text-gray-600">{error}</p>
          <p className="mt-4 text-sm text-gray-500">
            This link may have expired or already been used. Please contact your project manager
            if you need to provide a status update.
          </p>
        </Card>
      </div>
    );
  }

  // Success state
  if (submitted && submittedResponse) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="max-w-md w-full"
        >
          <Card className="p-8 text-center">
            <CheckCircle2 className="h-16 w-16 text-green-500 mx-auto" />
            <h1 className="mt-4 text-xl font-semibold text-gray-900">Response Submitted!</h1>
            <p className="mt-2 text-gray-600">
              Thank you for your update on{' '}
              <span className="font-medium">{validation?.work_item.name}</span>
            </p>
            
            <div className="mt-6 bg-gray-50 rounded-lg p-4 text-left">
              <h3 className="text-sm font-medium text-gray-700 mb-2">Your Response:</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Status:</span>
                  <Badge variant={selectedStatus === 'ON_TRACK' ? 'success' : 'warning'}>
                    {selectedStatus?.replace('_', ' ')}
                  </Badge>
                </div>
                {proposedDate && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">New Date:</span>
                    <span className="font-medium">{proposedDate}</span>
                  </div>
                )}
                {reasonCategory && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Reason:</span>
                    <span className="font-medium">{reasonCategory.replace('_', ' ')}</span>
                  </div>
                )}
              </div>
            </div>

            {validation?.can_update && (
              <p className="mt-4 text-xs text-gray-500">
                You can update your response until the deadline by using the same link.
              </p>
            )}
          </Card>
        </motion.div>
      </div>
    );
  }

  // FIX: Null safety - ensure validation data exists before rendering form
  if (!validation || !validation.work_item || !validation.responder) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full p-8 text-center">
          <AlertTriangle className="h-16 w-16 text-amber-500 mx-auto" />
          <h1 className="mt-4 text-xl font-semibold text-gray-900">Invalid Link</h1>
          <p className="mt-2 text-gray-600">
            Unable to load task information. The link may be invalid or expired.
          </p>
        </Card>
      </div>
    );
  }

  // Main form
  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-gray-900">Status Check</h1>
            <p className="mt-1 text-gray-600">
              Help us keep the project on track by sharing your progress
            </p>
          </div>
        </motion.div>

        {/* Work Item Context */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-blue-600" />
                Task Details
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-lg font-semibold text-gray-900">
                  {validation?.work_item.name}
                </p>
                <p className="text-sm text-gray-500 font-mono">
                  {validation?.work_item.external_id}
                </p>
              </div>
              
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Program:</span>
                  <p className="font-medium">{validation?.work_item.program_name || '-'}</p>
                </div>
                <div>
                  <span className="text-gray-500">Project:</span>
                  <p className="font-medium">{validation?.work_item.project_name || '-'}</p>
                </div>
                <div>
                  <span className="text-gray-500">Deadline:</span>
                  <p className="font-medium text-red-600">
                    {new Date(validation?.deadline || '').toLocaleDateString()}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Current Progress:</span>
                  <p className="font-medium">{validation?.work_item.completion_percent}%</p>
                </div>
              </div>

              {validation?.previous_response && (
                <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                  <div className="flex items-start gap-2">
                    <Info className="h-4 w-4 text-amber-600 mt-0.5" />
                    <div className="text-sm">
                      <p className="font-medium text-amber-800">Previous Response</p>
                      <p className="text-amber-700">
                        You reported <strong>{validation.previous_response.reported_status}</strong> on{' '}
                        {new Date(validation.previous_response.created_at).toLocaleDateString()}.
                        You can update your response below.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Responder Info */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <Card padding="sm">
            <div className="flex items-center gap-3 p-2">
              <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center">
                <User className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Responding as</p>
                <p className="font-medium text-gray-900">{validation?.responder.name}</p>
              </div>
            </div>
          </Card>
        </motion.div>

        {/* Status Selection */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Card>
            <CardHeader>
              <CardTitle>What's the status?</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {STATUS_OPTIONS.map((option) => {
                  const Icon = option.icon;
                  const isSelected = selectedStatus === option.value;
                  return (
                    <button
                      key={option.value}
                      onClick={() => setSelectedStatus(option.value)}
                      className={`
                        p-4 rounded-lg border-2 text-left transition-all
                        ${isSelected ? option.color + ' border-current' : 'border-gray-200 hover:border-gray-300'}
                      `}
                    >
                      <div className="flex items-start gap-3">
                        <Icon className={`h-5 w-5 ${isSelected ? '' : 'text-gray-400'}`} />
                        <div>
                          <p className={`font-medium ${isSelected ? '' : 'text-gray-900'}`}>
                            {option.label}
                          </p>
                          <p className={`text-sm ${isSelected ? 'opacity-80' : 'text-gray-500'}`}>
                            {option.description}
                          </p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Conditional: Delay Details */}
        {(selectedStatus === 'DELAYED' || selectedStatus === 'BLOCKED') && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-amber-600" />
                  {selectedStatus === 'DELAYED' ? 'Delay Details' : 'Blocker Details'}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* New Date */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {selectedStatus === 'DELAYED' 
                      ? 'When can you complete it?' 
                      : 'Expected resolution date'}
                    <span className="text-red-500 ml-1">*</span>
                  </label>
                  <Input
                    type="date"
                    value={proposedDate}
                    onChange={(e) => setProposedDate(e.target.value)}
                    min={minProposedDate}
                    className="max-w-xs"
                    required
                  />
                  {/* FIX: Show validation error for past dates */}
                  {proposedDate && proposedDate < today && (
                    <p className="mt-1 text-sm text-red-600">
                      Date cannot be in the past
                    </p>
                  )}
                </div>

                {/* Reason Category */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Primary Reason
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {REASON_CATEGORIES.map((reason) => (
                      <button
                        key={reason.value}
                        onClick={() => {
                          setReasonCategory(reason.value);
                          setReasonDetails({});
                        }}
                        className={`
                          p-2 text-xs rounded-lg border text-left transition-all
                          ${reasonCategory === reason.value 
                            ? 'border-blue-500 bg-blue-50 text-blue-700' 
                            : 'border-gray-200 hover:border-gray-300 text-gray-700'}
                        `}
                      >
                        <p className="font-medium">{reason.label}</p>
                      </button>
                    ))}
                  </div>
                  {reasonCategory && (
                    <p className="mt-2 text-sm text-gray-500">
                      {REASON_CATEGORIES.find(r => r.value === reasonCategory)?.description}
                    </p>
                  )}
                </div>

                {/* Conditional reason fields */}
                {reasonCategory === 'SCOPE_INCREASE' && (
                  <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Additional work percentage
                      </label>
                      <Input
                        type="number"
                        placeholder="e.g., 25"
                        value={reasonDetails.additional_work_percent || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          additional_work_percent: parseInt(e.target.value) || undefined
                        })}
                        className="max-w-[120px]"
                      />
                      <span className="ml-2 text-gray-500">%</span>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        What new requirements were discovered?
                      </label>
                      <textarea
                        className="w-full p-3 border border-gray-300 rounded-lg text-sm"
                        rows={2}
                        placeholder="Describe the additional scope..."
                        value={reasonDetails.new_requirements || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          new_requirements: e.target.value || undefined
                        })}
                      />
                    </div>
                  </div>
                )}

                {reasonCategory === 'RESOURCE_PULLED' && (
                  <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Available effort on this task
                      </label>
                      <Input
                        type="number"
                        placeholder="e.g., 50"
                        value={reasonDetails.available_effort_percent || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          available_effort_percent: parseInt(e.target.value) || undefined
                        })}
                        className="max-w-[120px]"
                      />
                      <span className="ml-2 text-gray-500">%</span>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Until when is effort reduced?
                      </label>
                      <Input
                        type="date"
                        value={reasonDetails.until_date || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          until_date: e.target.value || undefined
                        })}
                        className="max-w-xs"
                      />
                    </div>
                  </div>
                )}

                {reasonCategory === 'TECHNICAL_BLOCKER' && (
                  <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Describe the blocker
                      </label>
                      <textarea
                        className="w-full p-3 border border-gray-300 rounded-lg text-sm"
                        rows={2}
                        placeholder="What's blocking progress..."
                        value={reasonDetails.blocker_description || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          blocker_description: e.target.value || undefined
                        })}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Who can help unblock this?
                      </label>
                      <Input
                        type="text"
                        placeholder="Name or team..."
                        value={reasonDetails.needs_help_from || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          needs_help_from: e.target.value || undefined
                        })}
                      />
                    </div>
                  </div>
                )}

                {reasonCategory === 'EXTERNAL_DEPENDENCY' && (
                  <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Waiting for
                      </label>
                      <Input
                        type="text"
                        placeholder="External team, vendor, decision..."
                        value={reasonDetails.waiting_for || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          waiting_for: e.target.value || undefined
                        })}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Expected by
                      </label>
                      <Input
                        type="date"
                        value={reasonDetails.expected_date || ''}
                        onChange={(e) => setReasonDetails({
                          ...reasonDetails,
                          expected_date: e.target.value || undefined
                        })}
                        className="max-w-xs"
                      />
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Impact Analysis Preview */}
        {(selectedStatus === 'DELAYED' || selectedStatus === 'BLOCKED') && proposedDate && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card className={`border-2 ${
              impactAnalysis?.critical_path_affected 
                ? 'border-red-300 bg-red-50' 
                : impactAnalysis?.cascade_affected_items?.length 
                  ? 'border-amber-300 bg-amber-50'
                  : 'border-gray-200'
            }`}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className={`h-5 w-5 ${
                    impactAnalysis?.critical_path_affected 
                      ? 'text-red-600' 
                      : 'text-amber-600'
                  }`} />
                  Impact Preview
                </CardTitle>
              </CardHeader>
              <CardContent>
                {loadingImpact ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
                    <span className="ml-2 text-sm text-gray-500">Calculating impact...</span>
                  </div>
                ) : impactAnalysis ? (
                  <div className="space-y-4">
                    {/* Delay Summary */}
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-gray-500">Delay Duration:</span>
                        <p className="font-bold text-lg text-amber-600">
                          {impactAnalysis.direct_delay_days || impactAnalysis.delay_days || 0} days
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500">Affected Items:</span>
                        <p className="font-bold text-lg">
                          {impactAnalysis.cascade_affected_items?.length || impactAnalysis.cascade_count || 0}
                        </p>
                      </div>
                    </div>

                    {/* Critical Path Warning */}
                    {(impactAnalysis.critical_path_affected || impactAnalysis.is_critical_path) && (
                      <div className="flex items-start gap-2 p-3 bg-red-100 text-red-800 rounded-lg">
                        <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-semibold">Critical Path Affected</p>
                          <p className="text-sm">
                            This delay will impact project milestones and overall timeline.
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Affected Items */}
                    {impactAnalysis.cascade_affected_items?.length > 0 && (
                      <div>
                        <p className="text-sm font-medium text-gray-700 mb-2">
                          Downstream tasks that may be affected:
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {impactAnalysis.cascade_affected_items.slice(0, 5).map((itemId, index) => (
                            <span
                              key={index}
                              className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded font-mono"
                            >
                              {itemId}
                            </span>
                          ))}
                          {impactAnalysis.cascade_affected_items.length > 5 && (
                            <span className="px-2 py-1 text-gray-500 text-xs">
                              +{impactAnalysis.cascade_affected_items.length - 5} more
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Recommendation */}
                    {impactAnalysis.recommendation && (
                      <div className="p-3 bg-blue-50 text-blue-800 rounded-lg text-sm">
                        <p className="font-medium">Recommendation:</p>
                        <p>{impactAnalysis.recommendation}</p>
                      </div>
                    )}

                    {/* Risk Level Badge */}
                    {impactAnalysis.risk_level && (
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-500">Risk Level:</span>
                        <Badge variant={
                          impactAnalysis.risk_level === 'CRITICAL' ? 'danger' :
                          impactAnalysis.risk_level === 'HIGH' ? 'warning' :
                          impactAnalysis.risk_level === 'MEDIUM' ? 'warning' : 'default'
                        }>
                          {impactAnalysis.risk_level}
                        </Badge>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 py-4 text-center">
                    Enter a new date to see the impact analysis
                  </p>
                )}
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Comment */}
        {selectedStatus && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Additional Comments (Optional)</CardTitle>
              </CardHeader>
              <CardContent>
                <textarea
                  className="w-full p-3 border border-gray-300 rounded-lg text-sm"
                  rows={3}
                  placeholder="Any additional context you'd like to share..."
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Submit */}
        {selectedStatus && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-end gap-2 pb-8"
          >
            {/* FIX: Show validation errors */}
            {!isFormValid() && (selectedStatus === 'DELAYED' || selectedStatus === 'BLOCKED') && (
              <p className="text-sm text-amber-600">
                {!proposedDate && 'Please select a proposed date. '}
                {proposedDate && proposedDate < today && 'Proposed date cannot be in the past. '}
                {!reasonCategory && 'Please select a reason category.'}
              </p>
            )}
            <Button
              onClick={handleSubmit}
              disabled={submitting || !isFormValid()}
              className="min-w-[200px]"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Submit Response
                </>
              )}
            </Button>
          </motion.div>
        )}
      </div>
    </div>
  );
}

export default AlertResponsePage;
