/**
 * Alerts Dashboard Page - PM Command Center for Proactive Tracking
 * 
 * Features:
 * - View all alerts and their status
 * - Approve/reject delay requests
 * - Monitor escalation chains
 * - Trigger manual alerts
 * - Run daily scan manually
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Bell,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Send,
  User,
  Calendar,
  ThumbsUp,
  ThumbsDown,
  Play,
  Loader2,
} from 'lucide-react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '../lib/api';
import { cn, formatRelativeTime } from '../lib/utils';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../components/ui/Toast';
import type { Alert, WorkItemResponse, AlertStatus } from '../types';

// Status badge mapping
const STATUS_COLORS: Record<AlertStatus, string> = {
  PENDING: 'default',
  SENT: 'info',
  DELIVERED: 'info',
  OPENED: 'primary',
  RESPONDED: 'success',
  EXPIRED: 'danger',
  CANCELLED: 'default',
};

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export function AlertsPage() {
  const toast = useToast();
  
  // State
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [selectedResponse, setSelectedResponse] = useState<WorkItemResponse | null>(null);
  const [approvalAction, setApprovalAction] = useState<'approve' | 'reject'>('approve');
  const [rejectionReason, setRejectionReason] = useState('');

  // Queries
  const { data: alertsData, isLoading: alertsLoading, refetch: refetchAlerts } = useQuery({
    queryKey: ['alerts', statusFilter],
    queryFn: () => api.alerts.list({ status: statusFilter || undefined }),
  });

  const { data: approvalsData, isLoading: approvalsLoading, refetch: refetchApprovals } = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: () => api.alerts.pendingApprovals(),
  });

  const { data: dueTomorrowData, isLoading: dueTomorrowLoading } = useQuery({
    queryKey: ['due-tomorrow'],
    queryFn: () => api.alerts.dueTomorrow(),
  });

  // Mutations
  const runScanMutation = useMutation({
    mutationFn: () => api.alerts.runScan(),
    onSuccess: (data) => {
      toast.success(`Scan complete: ${data.alerts_created} alerts created`);
      refetchAlerts();
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to run scan');
    },
  });

  const processApprovalMutation = useMutation({
    mutationFn: ({ responseId, action, reason }: { responseId: string; action: 'approve' | 'reject'; reason?: string }) =>
      api.alerts.processApproval(responseId, action, reason),
    onSuccess: () => {
      toast.success(approvalAction === 'approve' ? 'Response approved' : 'Response rejected');
      setShowApprovalModal(false);
      setSelectedResponse(null);
      setRejectionReason('');
      refetchApprovals();
      refetchAlerts();
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to process approval');
    },
  });

  const triggerAlertMutation = useMutation({
    mutationFn: (workItemId: string) => api.alerts.triggerManual(workItemId, 'NORMAL'),
    onSuccess: () => {
      toast.success('Alert triggered successfully');
      refetchAlerts();
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to trigger alert');
    },
  });

  // Handlers
  const handleApproval = (response: WorkItemResponse, action: 'approve' | 'reject') => {
    setSelectedResponse(response);
    setApprovalAction(action);
    setShowApprovalModal(true);
  };

  const confirmApproval = () => {
    if (!selectedResponse) return;
    processApprovalMutation.mutate({
      responseId: selectedResponse.id,
      action: approvalAction,
      reason: approvalAction === 'reject' ? rejectionReason : undefined,
    });
  };

  // Stats
  const alertStats = {
    total: alertsData?.count || 0,
    pending: alertsData?.pending_count || 0,
    responded: alertsData?.responded_count || 0,
    pendingApprovals: approvalsData?.count || 0,
    dueTomorrow: dueTomorrowData?.count || 0,
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="p-6 space-y-6 max-w-7xl mx-auto"
    >
      {/* Header */}
      <motion.div variants={itemVariants} className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Bell className="h-6 w-6 text-blue-600" />
            Proactive Alerts
          </h1>
          <p className="mt-1 text-gray-600 dark:text-gray-400">
            Monitor status checks and approve delay requests
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {
              refetchAlerts();
              refetchApprovals();
            }}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button
            onClick={() => runScanMutation.mutate()}
            disabled={runScanMutation.isPending}
          >
            {runScanMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Run Daily Scan
          </Button>
        </div>
      </motion.div>

      {/* KPI Cards */}
      <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <StatCard
          title="Total Alerts"
          value={alertStats.total}
          icon={<Bell className="h-5 w-5" />}
          color="blue"
        />
        <StatCard
          title="Awaiting Response"
          value={alertStats.pending}
          icon={<Clock className="h-5 w-5" />}
          color="amber"
        />
        <StatCard
          title="Responded"
          value={alertStats.responded}
          icon={<CheckCircle2 className="h-5 w-5" />}
          color="green"
        />
        <StatCard
          title="Pending Approvals"
          value={alertStats.pendingApprovals}
          icon={<AlertTriangle className="h-5 w-5" />}
          color="red"
          highlight={alertStats.pendingApprovals > 0}
        />
        <StatCard
          title="Due Tomorrow"
          value={alertStats.dueTomorrow}
          icon={<Calendar className="h-5 w-5" />}
          color="purple"
        />
      </motion.div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pending Approvals - Takes priority */}
        <motion.div variants={itemVariants} className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                Pending Approvals
                {alertStats.pendingApprovals > 0 && (
                  <Badge variant="danger">{alertStats.pendingApprovals}</Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {approvalsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
                </div>
              ) : !approvalsData?.approvals?.length ? (
                <div className="text-center py-8 text-gray-500">
                  <CheckCircle2 className="h-12 w-12 mx-auto text-green-300" />
                  <p className="mt-2">No pending approvals</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {approvalsData.approvals.map((response) => (
                    <ApprovalCard
                      key={response.id}
                      response={response}
                      onApprove={() => handleApproval(response, 'approve')}
                      onReject={() => handleApproval(response, 'reject')}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Due Tomorrow Sidebar */}
        <motion.div variants={itemVariants}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-purple-600" />
                Due Tomorrow
              </CardTitle>
            </CardHeader>
            <CardContent>
              {dueTomorrowLoading ? (
                <div className="flex justify-center py-4">
                  <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                </div>
              ) : !dueTomorrowData?.items?.length ? (
                <p className="text-center py-4 text-gray-500 text-sm">No items due tomorrow</p>
              ) : (
                <div className="space-y-2">
                  {dueTomorrowData.items.slice(0, 5).map((item) => (
                    <div
                      key={item.work_item_id}
                      className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800"
                    >
                      <div className="flex justify-between items-start">
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-sm truncate">{item.work_item_name}</p>
                          <p className="text-xs text-gray-500">{item.resource_name}</p>
                        </div>
                        {item.alert_exists ? (
                          <Badge variant="info" size="sm">Alert Sent</Badge>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => triggerAlertMutation.mutate(item.work_item_id)}
                            disabled={triggerAlertMutation.isPending}
                          >
                            <Send className="h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                  {dueTomorrowData.items.length > 5 && (
                    <p className="text-xs text-center text-gray-500">
                      +{dueTomorrowData.items.length - 5} more
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* All Alerts */}
      <motion.div variants={itemVariants}>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5 text-blue-600" />
              All Alerts
            </CardTitle>
            <div className="flex gap-2">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              >
                <option value="">All Statuses</option>
                <option value="PENDING">Pending</option>
                <option value="SENT">Sent</option>
                <option value="DELIVERED">Delivered</option>
                <option value="OPENED">Opened</option>
                <option value="RESPONDED">Responded</option>
                <option value="EXPIRED">Expired</option>
              </select>
            </div>
          </CardHeader>
          <CardContent>
            {alertsLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
              </div>
            ) : !alertsData?.alerts?.length ? (
              <div className="text-center py-8 text-gray-500">
                <Bell className="h-12 w-12 mx-auto text-gray-300" />
                <p className="mt-2">No alerts found</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <th className="pb-3">Work Item</th>
                      <th className="pb-3">Recipient</th>
                      <th className="pb-3">Deadline</th>
                      <th className="pb-3">Status</th>
                      <th className="pb-3">Escalation</th>
                      <th className="pb-3">Sent</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {alertsData.alerts.map((alert) => (
                      <AlertRow key={alert.id} alert={alert} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Approval Modal */}
      <Modal
        isOpen={showApprovalModal}
        onClose={() => {
          setShowApprovalModal(false);
          setSelectedResponse(null);
          setRejectionReason('');
        }}
        title={approvalAction === 'approve' ? 'Approve Delay Request' : 'Reject Delay Request'}
      >
        {selectedResponse && (
          <div className="space-y-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="font-medium">{selectedResponse.work_item_name}</p>
              <p className="text-sm text-gray-500 mt-1">
                Requested by: {selectedResponse.responder_name}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Status:</span>
                  <span className="ml-2 font-medium">{selectedResponse.reported_status}</span>
                </div>
                {selectedResponse.proposed_new_date && (
                  <div>
                    <span className="text-gray-500">New Date:</span>
                    <span className="ml-2 font-medium">{selectedResponse.proposed_new_date}</span>
                  </div>
                )}
                {selectedResponse.reason_category && (
                  <div className="col-span-2">
                    <span className="text-gray-500">Reason:</span>
                    <span className="ml-2 font-medium">
                      {selectedResponse.reason_category.replace('_', ' ')}
                    </span>
                  </div>
                )}
              </div>
              {selectedResponse.comment && (
                <div className="mt-3 p-2 bg-white rounded border text-sm">
                  <p className="text-gray-500 text-xs mb-1">Comment:</p>
                  <p>{selectedResponse.comment}</p>
                </div>
              )}
            </div>

            {approvalAction === 'reject' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Rejection Reason
                </label>
                <textarea
                  className="w-full p-3 border border-gray-300 rounded-lg text-sm"
                  rows={3}
                  placeholder="Explain why this is being rejected..."
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                />
              </div>
            )}

            <div className="flex justify-end gap-3 pt-4">
              <Button
                variant="outline"
                onClick={() => {
                  setShowApprovalModal(false);
                  setSelectedResponse(null);
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={confirmApproval}
                disabled={processApprovalMutation.isPending || (approvalAction === 'reject' && !rejectionReason)}
                className={approvalAction === 'approve' ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'}
              >
                {processApprovalMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : approvalAction === 'approve' ? (
                  <ThumbsUp className="h-4 w-4 mr-2" />
                ) : (
                  <ThumbsDown className="h-4 w-4 mr-2" />
                )}
                {approvalAction === 'approve' ? 'Approve' : 'Reject'}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </motion.div>
  );
}

// Stat Card Component
function StatCard({
  title,
  value,
  icon,
  color,
  highlight = false,
}: {
  title: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  highlight?: boolean;
}) {
  const colorClasses = {
    blue: 'text-blue-600 bg-blue-50',
    green: 'text-green-600 bg-green-50',
    amber: 'text-amber-600 bg-amber-50',
    red: 'text-red-600 bg-red-50',
    purple: 'text-purple-600 bg-purple-50',
  };

  return (
    <Card className={cn(highlight && 'ring-2 ring-red-200 border-red-300')}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className={cn('p-2 rounded-lg', colorClasses[color as keyof typeof colorClasses])}>
            {icon}
          </div>
          <span className="text-2xl font-bold">{value}</span>
        </div>
        <p className="mt-2 text-sm text-gray-600">{title}</p>
      </CardContent>
    </Card>
  );
}

// Approval Card Component
function ApprovalCard({
  response,
  onApprove,
  onReject,
}: {
  response: WorkItemResponse;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <div className="p-4 rounded-lg border border-amber-200 bg-amber-50/50">
      <div className="flex justify-between items-start">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-gray-900">{response.work_item_name}</p>
          <p className="text-sm text-gray-500">{response.work_item_external_id}</p>
        </div>
        <Badge variant="warning">{response.reported_status}</Badge>
      </div>
      
      <div className="mt-3 flex items-center gap-4 text-sm text-gray-600">
        <span className="flex items-center gap-1">
          <User className="h-3 w-3" />
          {response.responder_name}
        </span>
        {response.proposed_new_date && (
          <span className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            {response.proposed_new_date}
          </span>
        )}
        {response.delay_days && (
          <span className="text-red-600">+{response.delay_days} days</span>
        )}
      </div>

      {response.reason_category && (
        <div className="mt-2">
          <Badge variant="default" size="sm">
            {response.reason_category.replace('_', ' ')}
          </Badge>
        </div>
      )}

      {response.comment && (
        <p className="mt-2 text-sm text-gray-600 italic">"{response.comment}"</p>
      )}

      <div className="mt-4 flex gap-2">
        <Button size="sm" onClick={onApprove} className="bg-green-600 hover:bg-green-700">
          <ThumbsUp className="h-3 w-3 mr-1" />
          Approve
        </Button>
        <Button size="sm" variant="outline" onClick={onReject} className="border-red-300 text-red-600 hover:bg-red-50">
          <ThumbsDown className="h-3 w-3 mr-1" />
          Reject
        </Button>
      </div>
    </div>
  );
}

// Alert Row Component
function AlertRow({ alert }: { alert: Alert }) {
  const statusVariant = STATUS_COLORS[alert.status] || 'default';
  
  return (
    <tr className="text-sm">
      <td className="py-3">
        <div>
          <p className="font-medium text-gray-900">{alert.work_item_name || 'Unknown'}</p>
          <p className="text-xs text-gray-500">{alert.work_item_external_id}</p>
        </div>
      </td>
      <td className="py-3">
        <p>{alert.actual_recipient_name || alert.intended_recipient_name || '-'}</p>
      </td>
      <td className="py-3">
        <p>{new Date(alert.deadline_date).toLocaleDateString()}</p>
      </td>
      <td className="py-3">
        <Badge variant={statusVariant as any}>{alert.status}</Badge>
      </td>
      <td className="py-3">
        <span className="text-gray-500">Level {alert.escalation_level}</span>
      </td>
      <td className="py-3 text-gray-500">
        {alert.sent_at ? formatRelativeTime(alert.sent_at) : '-'}
      </td>
    </tr>
  );
}

export default AlertsPage;
