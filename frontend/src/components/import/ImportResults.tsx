/**
 * Import Results component - Shows the outcome of an import operation
 */
import { motion } from 'framer-motion';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  Clock,
  Plus,
  RefreshCw,
  Shield,
  XOctagon,
  Flag,
  Zap,
  Users,
  GitBranch,
} from 'lucide-react';
import { cn, formatNumber, formatDuration } from '../../lib/utils';
import { Card, Button } from '../ui';
import type { ImportResponse } from '../../types';

interface ImportResultsProps {
  result: ImportResponse;
  onViewFlagged?: () => void;
  onViewAuditLog?: () => void;
}

export function ImportResults({
  result,
  onViewFlagged,
  onViewAuditLog,
}: ImportResultsProps) {
  const { status, summary, warnings, flagged_items, execution_time_ms } = result;

  const isSuccess = status === 'success' || status === 'partial_success';
  const hasWarnings = warnings.length > 0;
  const hasFlagged = flagged_items.length > 0;

  // Calculate totals
  const totalTasks =
    summary.tasks_created +
    summary.tasks_updated +
    summary.tasks_preserved +
    summary.tasks_cancelled +
    summary.tasks_flagged;

  return (
    <div className="space-y-6">
      {/* Status Banner */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className={cn(
          'rounded-2xl p-6 border-2',
          isSuccess
            ? 'bg-gradient-to-br from-green-50 to-emerald-50 border-green-200 dark:from-green-900/20 dark:to-emerald-900/20 dark:border-green-800'
            : 'bg-gradient-to-br from-red-50 to-rose-50 border-red-200 dark:from-red-900/20 dark:to-rose-900/20 dark:border-red-800'
        )}
      >
        <div className="flex items-center gap-4">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
            className={cn(
              'p-4 rounded-2xl',
              isSuccess
                ? 'bg-green-100 dark:bg-green-900/30'
                : 'bg-red-100 dark:bg-red-900/30'
            )}
          >
            {isSuccess ? (
              <CheckCircle2 className="h-10 w-10 text-green-500" />
            ) : (
              <XCircle className="h-10 w-10 text-red-500" />
            )}
          </motion.div>
          <div>
            <h2
              className={cn(
                'text-2xl font-bold',
                isSuccess
                  ? 'text-green-800 dark:text-green-200'
                  : 'text-red-800 dark:text-red-200'
              )}
            >
              {status === 'success'
                ? 'Import Successful!'
                : status === 'partial_success'
                ? 'Import Completed with Warnings'
                : 'Import Failed'}
            </h2>
            <div className="mt-1 flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
              <span className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                {formatDuration(execution_time_ms)}
              </span>
              {result.import_batch_id && (
                <span className="flex items-center gap-1">
                  <FileText className="h-4 w-4" />
                  Batch: {result.import_batch_id.slice(0, 8)}...
                </span>
              )}
            </div>
          </div>
        </div>
      </motion.div>

      {/* Work Items Summary */}
      <Card variant="elevated" padding="lg">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Work Items Summary
        </h3>

        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <StatCard
            icon={<Plus />}
            label="Created"
            value={summary.tasks_created}
            color="green"
            description="New tasks added"
          />
          <StatCard
            icon={<RefreshCw />}
            label="Updated"
            value={summary.tasks_updated}
            color="blue"
            description="Baselines synced"
          />
          <StatCard
            icon={<Shield />}
            label="Preserved"
            value={summary.tasks_preserved}
            color="purple"
            description="Current dates kept"
          />
          <StatCard
            icon={<XOctagon />}
            label="Cancelled"
            value={summary.tasks_cancelled}
            color="gray"
            description="Ghost tasks"
          />
          <StatCard
            icon={<Flag />}
            label="Flagged"
            value={summary.tasks_flagged}
            color="amber"
            description="Needs PM review"
            onClick={hasFlagged ? onViewFlagged : undefined}
          />
        </div>

        {/* Visual Progress */}
        {totalTasks > 0 && (
          <div className="mt-6">
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-2">
              <span>Import Distribution</span>
              <span>{formatNumber(totalTasks)} total work items</span>
            </div>
            <div className="flex h-3 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-800">
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${(summary.tasks_created / totalTasks) * 100}%`,
                }}
                transition={{ delay: 0.3, duration: 0.5 }}
                className="bg-green-500"
                title={`Created: ${summary.tasks_created}`}
              />
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${(summary.tasks_updated / totalTasks) * 100}%`,
                }}
                transition={{ delay: 0.4, duration: 0.5 }}
                className="bg-blue-500"
                title={`Updated: ${summary.tasks_updated}`}
              />
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${(summary.tasks_preserved / totalTasks) * 100}%`,
                }}
                transition={{ delay: 0.5, duration: 0.5 }}
                className="bg-purple-500"
                title={`Preserved: ${summary.tasks_preserved}`}
              />
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${(summary.tasks_cancelled / totalTasks) * 100}%`,
                }}
                transition={{ delay: 0.6, duration: 0.5 }}
                className="bg-gray-400"
                title={`Cancelled: ${summary.tasks_cancelled}`}
              />
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${(summary.tasks_flagged / totalTasks) * 100}%`,
                }}
                transition={{ delay: 0.7, duration: 0.5 }}
                className="bg-amber-500"
                title={`Flagged: ${summary.tasks_flagged}`}
              />
            </div>
            <div className="flex gap-4 mt-3 flex-wrap">
              <LegendItem color="bg-green-500" label="Created" />
              <LegendItem color="bg-blue-500" label="Updated" />
              <LegendItem color="bg-purple-500" label="Preserved" />
              <LegendItem color="bg-gray-400" label="Cancelled" />
              <LegendItem color="bg-amber-500" label="Flagged" />
            </div>
          </div>
        )}
      </Card>

      {/* Other Synced Data */}
      <Card variant="default" padding="lg">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Additional Sync Results
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MiniStat
            icon={<FileText className="h-4 w-4" />}
            label="Programs"
            value={summary.programs_synced}
          />
          <MiniStat
            icon={<FileText className="h-4 w-4" />}
            label="Projects"
            value={summary.projects_synced}
          />
          <MiniStat
            icon={<Users className="h-4 w-4" />}
            label="Resources"
            value={summary.resources_synced}
          />
          <MiniStat
            icon={<GitBranch className="h-4 w-4" />}
            label="Dependencies"
            value={summary.dependencies_synced}
          />
        </div>

        {/* Recalculation Stats */}
        {summary.recalculation_time_ms > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <Zap className="h-4 w-4 text-amber-500" />
              <span>
                Critical path recalculated in{' '}
                <strong>{formatDuration(summary.recalculation_time_ms)}</strong>
                {summary.critical_path_items > 0 && (
                  <> • {formatNumber(summary.critical_path_items)} items on critical path</>
                )}
              </span>
            </div>
          </div>
        )}
      </Card>

      {/* Warnings */}
      {hasWarnings && (
        <Card variant="default" padding="lg" className="border-amber-200 dark:border-amber-800/50">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Warnings ({warnings.length})
            </h3>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {warnings.slice(0, 10).map((warning, index) => (
              <div
                key={index}
                className="flex items-start gap-2 p-2 rounded-lg bg-amber-50 dark:bg-amber-900/10"
              >
                <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  {typeof warning === 'string' ? warning : warning.message}
                </p>
              </div>
            ))}
            {warnings.length > 10 && (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
                +{warnings.length - 10} more warnings
              </p>
            )}
          </div>
        </Card>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3 justify-end">
        {onViewAuditLog && (
          <Button variant="outline" onClick={onViewAuditLog}>
            <FileText className="h-4 w-4" />
            View Audit Log
          </Button>
        )}
        {hasFlagged && onViewFlagged && (
          <Button variant="secondary" onClick={onViewFlagged}>
            <Flag className="h-4 w-4" />
            Review Flagged Items ({flagged_items.length})
          </Button>
        )}
      </div>
    </div>
  );
}

// Stat Card Component
interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: 'green' | 'blue' | 'purple' | 'gray' | 'amber';
  description: string;
  onClick?: () => void;
}

function StatCard({ icon, label, value, color, description, onClick }: StatCardProps) {
  const colors = {
    green: {
      bg: 'bg-green-50 dark:bg-green-900/20',
      icon: 'text-green-500',
      value: 'text-green-700 dark:text-green-300',
    },
    blue: {
      bg: 'bg-blue-50 dark:bg-blue-900/20',
      icon: 'text-blue-500',
      value: 'text-blue-700 dark:text-blue-300',
    },
    purple: {
      bg: 'bg-purple-50 dark:bg-purple-900/20',
      icon: 'text-purple-500',
      value: 'text-purple-700 dark:text-purple-300',
    },
    gray: {
      bg: 'bg-gray-50 dark:bg-gray-800/50',
      icon: 'text-gray-500',
      value: 'text-gray-700 dark:text-gray-300',
    },
    amber: {
      bg: 'bg-amber-50 dark:bg-amber-900/20',
      icon: 'text-amber-500',
      value: 'text-amber-700 dark:text-amber-300',
    },
  };

  const style = colors[color];

  const Wrapper = onClick ? 'button' : 'div';

  return (
    <Wrapper
      onClick={onClick}
      className={cn(
        'p-4 rounded-xl text-left transition-all',
        style.bg,
        onClick && 'hover:scale-105 cursor-pointer'
      )}
    >
      <div className={cn('mb-2', style.icon)}>
        {icon}
      </div>
      <p className={cn('text-3xl font-bold', style.value)}>
        {formatNumber(value)}
      </p>
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </p>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
        {description}
      </p>
    </Wrapper>
  );
}

// Mini Stat Component
function MiniStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
      <div className="text-gray-400">{icon}</div>
      <div>
        <p className="text-lg font-semibold text-gray-900 dark:text-white">
          {formatNumber(value)}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      </div>
    </div>
  );
}

// Legend Item
function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
      <div className={cn('h-2 w-2 rounded-full', color)} />
      <span>{label}</span>
    </div>
  );
}
