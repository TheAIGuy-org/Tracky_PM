/**
 * Audit Logs Page
 * View system activity and change history
 */
import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  History,
  Search,
  Calendar,
  User,
  FileSpreadsheet,
  GitMerge,
  AlertCircle,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Download,
  RefreshCw,
} from 'lucide-react';
import { useAuditLogs } from '../lib/queries';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Skeleton } from '../components/ui/Progress';
import { cn, formatDateTime, formatRelativeTime } from '../lib/utils';
import type { AuditLog } from '../types';

type ActionFilter = 'all' | 'import' | 'merge' | 'validation' | 'system';

// Helper to get timestamp from AuditLog (handles both changed_at and timestamp alias)
const getTimestamp = (log: AuditLog): string | undefined => log.timestamp || log.changed_at;
const getUser = (log: AuditLog): string | undefined => log.user || log.changed_by;
const getBatchId = (log: AuditLog): string | undefined => log.batch_id || log.import_batch_id;
const getDetails = (log: AuditLog): string | undefined => {
  if (log.details) return log.details;
  if (log.reason) return log.reason;
  if (log.field_changed) {
    return `${log.field_changed}: ${log.old_value || '(empty)'} → ${log.new_value || '(empty)'}`;
  }
  return undefined;
};

export function AuditLogsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [actionFilter, setActionFilter] = useState<ActionFilter>('all');
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());
  const [dateRange, setDateRange] = useState<'today' | 'week' | 'month' | 'all'>('week');

  const { data: auditLogsData, isLoading, refetch } = useAuditLogs();
  
  // Extract data from paginated response
  const auditLogs = auditLogsData?.data || [];

  // Filter logs
  const filteredLogs = useMemo(() => {
    if (!auditLogs || auditLogs.length === 0) return [];

    return auditLogs.filter((log) => {
      // Search filter
      const details = getDetails(log);
      if (
        searchQuery &&
        !log.action.toLowerCase().includes(searchQuery.toLowerCase()) &&
        !details?.toLowerCase().includes(searchQuery.toLowerCase())
      ) {
        return false;
      }

      // Action filter
      if (actionFilter !== 'all') {
        const action = log.action.toLowerCase();
        if (actionFilter === 'import' && !action.includes('import') && !action.includes('upload')) return false;
        if (actionFilter === 'merge' && !action.includes('merge')) return false;
        if (actionFilter === 'validation' && !action.includes('validat')) return false;
        if (actionFilter === 'system' && !action.includes('system') && !action.includes('recalc')) return false;
      }

      // Date filter
      const timestamp = getTimestamp(log);
      if (dateRange !== 'all' && timestamp) {
        const logDate = new Date(timestamp);
        const now = new Date();
        
        if (dateRange === 'today') {
          const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
          if (logDate < today) return false;
        } else if (dateRange === 'week') {
          const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
          if (logDate < weekAgo) return false;
        } else if (dateRange === 'month') {
          const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
          if (logDate < monthAgo) return false;
        }
      }

      return true;
    });
  }, [auditLogs, searchQuery, actionFilter, dateRange]);

  // Group logs by date
  const groupedLogs = useMemo(() => {
    const groups: Record<string, AuditLog[]> = {};
    
    filteredLogs.forEach((log) => {
      const timestamp = getTimestamp(log);
      const date = timestamp
        ? new Date(timestamp).toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })
        : 'Unknown Date';
      
      if (!groups[date]) {
        groups[date] = [];
      }
      groups[date].push(log);
    });

    return groups;
  }, [filteredLogs]);

  const toggleExpanded = (logId: string) => {
    setExpandedLogs((prev) => {
      const next = new Set(prev);
      if (next.has(logId)) {
        next.delete(logId);
      } else {
        next.add(logId);
      }
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Audit Logs
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Track all system activities and changes
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
          <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center justify-between px-6 py-3 bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search logs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-2 w-64 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Action filter */}
          <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {([
              { key: 'all', label: 'All' },
              { key: 'import', label: 'Imports' },
              { key: 'merge', label: 'Merges' },
              { key: 'validation', label: 'Validations' },
              { key: 'system', label: 'System' },
            ] as const).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setActionFilter(key)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                  actionFilter === key
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Date range filter */}
          <div className="flex items-center gap-2 text-sm">
            <Calendar className="w-4 h-4 text-gray-400" />
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value as typeof dateRange)}
              className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="today">Today</option>
              <option value="week">Last 7 days</option>
              <option value="month">Last 30 days</option>
              <option value="all">All time</option>
            </select>
          </div>
        </div>

        <span className="text-sm text-gray-500">
          {filteredLogs.length} log entries
        </span>
      </div>

      {/* Logs Timeline */}
      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="space-y-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Card key={i} className="p-4">
                <div className="flex items-start gap-4">
                  <Skeleton className="w-10 h-10 rounded-full" />
                  <div className="flex-1">
                    <Skeleton className="h-4 w-1/3 mb-2" />
                    <Skeleton className="h-3 w-2/3 mb-2" />
                    <Skeleton className="h-3 w-1/4" />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <History className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">No logs found</p>
            <p className="text-sm">Try adjusting your filters</p>
          </div>
        ) : (
          <div className="space-y-8">
            {Object.entries(groupedLogs).map(([date, logs]) => (
              <div key={date}>
                {/* Date header */}
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
                  <span className="text-sm font-medium text-gray-500 dark:text-gray-400 px-3">
                    {date}
                  </span>
                  <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
                </div>

                {/* Logs for this date */}
                <div className="space-y-3">
                  {logs.map((log, index) => (
                    <AuditLogCard
                      key={log.id || index}
                      log={log}
                      index={index}
                      isExpanded={expandedLogs.has(String(log.id))}
                      onToggle={() => toggleExpanded(String(log.id))}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Audit Log Card Component
interface AuditLogCardProps {
  log: AuditLog;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}

function AuditLogCard({ log, index, isExpanded, onToggle }: AuditLogCardProps) {
  const actionConfig = getActionConfig(log.action);

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card className="overflow-hidden">
        <div
          className={cn(
            'flex items-start gap-4 p-4 cursor-pointer transition-colors',
            isExpanded ? 'bg-gray-50 dark:bg-gray-800/50' : 'hover:bg-gray-50 dark:hover:bg-gray-800/30'
          )}
          onClick={onToggle}
        >
          {/* Icon */}
          <div
            className={cn(
              'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0',
              actionConfig.bgColor
            )}
          >
            <actionConfig.icon className={cn('w-5 h-5', actionConfig.iconColor)} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-gray-900 dark:text-gray-100">
                {log.action}
              </span>
              <Badge variant={actionConfig.variant as 'success' | 'primary' | 'warning' | 'danger' | 'secondary'} size="sm">
                {actionConfig.label}
              </Badge>
            </div>
            
            {getDetails(log) && (
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 truncate">
                {getDetails(log)}
              </p>
            )}

            <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
              {getUser(log) && (
                <span className="flex items-center gap-1">
                  <User className="w-3 h-3" />
                  {getUser(log)}
                </span>
              )}
              {getTimestamp(log) && (
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  {formatRelativeTime(getTimestamp(log)!)}
                </span>
              )}
              {getBatchId(log) && (
                <span className="flex items-center gap-1">
                  <FileSpreadsheet className="w-3 h-3" />
                  Batch: {getBatchId(log)!.substring(0, 8)}...
                </span>
              )}
            </div>
          </div>

          {/* Expand indicator */}
          <div className="flex-shrink-0">
            {isExpanded ? (
              <ChevronDown className="w-5 h-5 text-gray-400" />
            ) : (
              <ChevronRight className="w-5 h-5 text-gray-400" />
            )}
          </div>
        </div>

        {/* Expanded details */}
        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 pt-2 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/30">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      Full Timestamp
                    </label>
                    <p className="text-gray-900 dark:text-gray-100">
                      {formatDateTime(getTimestamp(log))}
                    </p>
                  </div>
                  {getBatchId(log) && (
                    <div>
                      <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        Batch ID
                      </label>
                      <p className="text-gray-900 dark:text-gray-100 font-mono text-xs">
                        {getBatchId(log)}
                      </p>
                    </div>
                  )}
                  {log.affected_items !== undefined && (
                    <div>
                      <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        Affected Items
                      </label>
                      <p className="text-gray-900 dark:text-gray-100">
                        {log.affected_items}
                      </p>
                    </div>
                  )}
                  {log.source_file && (
                    <div>
                      <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        Source File
                      </label>
                      <p className="text-gray-900 dark:text-gray-100">
                        {log.source_file}
                      </p>
                    </div>
                  )}
                </div>
                
                {getDetails(log) && (
                  <div className="mt-4">
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      Details
                    </label>
                    <p className="text-gray-900 dark:text-gray-100 mt-1 whitespace-pre-wrap">
                      {getDetails(log)}
                    </p>
                  </div>
                )}

                {log.metadata && (
                  <div className="mt-4">
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      Metadata
                    </label>
                    <pre className="mt-1 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg text-xs overflow-x-auto">
                      {JSON.stringify(log.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  );
}

// Helper function to get action configuration
function getActionConfig(action: string) {
  const actionLower = action.toLowerCase();

  if (actionLower.includes('import') || actionLower.includes('upload')) {
    return {
      icon: FileSpreadsheet,
      label: 'Import',
      variant: 'primary',
      bgColor: 'bg-blue-100 dark:bg-blue-900/30',
      iconColor: 'text-blue-600 dark:text-blue-400',
    };
  }

  if (actionLower.includes('merge')) {
    return {
      icon: GitMerge,
      label: 'Merge',
      variant: 'success',
      bgColor: 'bg-green-100 dark:bg-green-900/30',
      iconColor: 'text-green-600 dark:text-green-400',
    };
  }

  if (actionLower.includes('validat')) {
    return {
      icon: CheckCircle,
      label: 'Validation',
      variant: 'warning',
      bgColor: 'bg-amber-100 dark:bg-amber-900/30',
      iconColor: 'text-amber-600 dark:text-amber-400',
    };
  }

  if (actionLower.includes('error') || actionLower.includes('fail')) {
    return {
      icon: XCircle,
      label: 'Error',
      variant: 'danger',
      bgColor: 'bg-red-100 dark:bg-red-900/30',
      iconColor: 'text-red-600 dark:text-red-400',
    };
  }

  if (actionLower.includes('recalc') || actionLower.includes('system')) {
    return {
      icon: RefreshCw,
      label: 'System',
      variant: 'secondary',
      bgColor: 'bg-purple-100 dark:bg-purple-900/30',
      iconColor: 'text-purple-600 dark:text-purple-400',
    };
  }

  return {
    icon: AlertCircle,
    label: 'Activity',
    variant: 'secondary',
    bgColor: 'bg-gray-100 dark:bg-gray-700',
    iconColor: 'text-gray-600 dark:text-gray-400',
  };
}
