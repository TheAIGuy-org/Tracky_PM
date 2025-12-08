/**
 * Work Items Page
 * Main page for viewing and managing all work items
 */
import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  Upload,
  LayoutGrid,
  Table2,
  Calendar,
  BarChart3,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Layers,
  X,
} from 'lucide-react';
import { useWorkItems } from '../lib/queries';
import { WorkItemsTable } from '../components/table';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { Skeleton } from '../components/ui/Progress';
import { ImportWizard } from '../components/import/ImportWizard';
import type { WorkItem } from '../types';
import { cn, formatPercent } from '../lib/utils';

type ViewMode = 'table' | 'grid' | 'timeline' | 'analytics';

export function WorkItemsPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('table');
  const [showImportModal, setShowImportModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState<WorkItem | null>(null);

  const { data: workItemsData, isLoading, refetch } = useWorkItems();
  
  // Extract work items from paginated response
  const workItems = workItemsData?.data || [];

  // Calculate summary stats
  const stats = calculateStats(workItems);

  const handleRowClick = useCallback((item: WorkItem) => {
    setSelectedItem(item);
  }, []);

  const handleImportSuccess = useCallback(() => {
    setShowImportModal(false);
    refetch();
  }, [refetch]);

  return (
    <div className="flex flex-col h-full">
      {/* Page Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Work Items
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage and track all tasks across your programs
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* View mode toggles */}
          <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1" role="tablist" aria-label="View modes">
            {([
              { mode: 'table', icon: Table2, label: 'Table' },
              { mode: 'grid', icon: LayoutGrid, label: 'Grid' },
              { mode: 'timeline', icon: Calendar, label: 'Timeline' },
              { mode: 'analytics', icon: BarChart3, label: 'Analytics' },
            ] as const).map(({ mode, icon: Icon, label }) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1',
                  viewMode === mode
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                )}
                role="tab"
                aria-selected={viewMode === mode}
                aria-label={`${label} view`}
              >
                <Icon className="w-4 h-4" aria-hidden="true" />
                <span className="hidden lg:inline">{label}</span>
              </button>
            ))}
          </div>

          {/* Actions */}
          <Button variant="secondary" onClick={() => setShowImportModal(true)}>
            <Upload className="w-4 h-4 mr-2" aria-hidden="true" />
            Import
          </Button>
          <Button variant="primary">
            <Plus className="w-4 h-4 mr-2" aria-hidden="true" />
            New Task
          </Button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 px-6 py-4 bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-800">
        <StatCard
          icon={<Layers className="w-5 h-5 text-blue-600" />}
          label="Total Items"
          value={stats.total}
          isLoading={isLoading}
        />
        <StatCard
          icon={<Clock className="w-5 h-5 text-amber-600" />}
          label="In Progress"
          value={stats.inProgress}
          change={formatPercent(stats.inProgressPct)}
          isLoading={isLoading}
        />
        <StatCard
          icon={<CheckCircle2 className="w-5 h-5 text-green-600" />}
          label="Completed"
          value={stats.completed}
          change={formatPercent(stats.completedPct)}
          isLoading={isLoading}
        />
        <StatCard
          icon={<AlertTriangle className="w-5 h-5 text-red-600" />}
          label="Flagged"
          value={0}
          trend="warning"
          isLoading={isLoading}
        />
        <StatCard
          icon={<BarChart3 className="w-5 h-5 text-purple-600" />}
          label="Avg Progress"
          value={`${stats.avgProgress}%`}
          isLoading={isLoading}
        />
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden p-6">
        <AnimatePresence mode="wait">
          {viewMode === 'table' && (
            <motion.div
              key="table"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full"
            >
              <WorkItemsTable
                data={workItems}
                isLoading={isLoading}
                onRowClick={handleRowClick}
                onRefresh={() => refetch()}
              />
            </motion.div>
          )}

          {viewMode === 'grid' && (
            <motion.div
              key="grid"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full overflow-auto"
            >
              <WorkItemsGrid
                data={workItems}
                isLoading={isLoading}
                onItemClick={handleRowClick}
              />
            </motion.div>
          )}

          {viewMode === 'timeline' && (
            <motion.div
              key="timeline"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full flex items-center justify-center"
            >
              <ComingSoon feature="Timeline View" />
            </motion.div>
          )}

          {viewMode === 'analytics' && (
            <motion.div
              key="analytics"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full flex items-center justify-center"
            >
              <ComingSoon feature="Analytics View" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Import Modal */}
      <Modal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        size="xl"
      >
        <ImportWizard
          onComplete={handleImportSuccess}
          onCancel={() => setShowImportModal(false)}
        />
      </Modal>

      {/* Item Detail Drawer */}
      <AnimatePresence>
        {selectedItem && (
          <WorkItemDrawer
            item={selectedItem}
            onClose={() => setSelectedItem(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// Helper Components

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  change?: string;
  trend?: 'up' | 'down' | 'warning';
  isLoading?: boolean;
}

function StatCard({ icon, label, value, change, trend, isLoading }: StatCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
          {icon}
        </div>
        <div className="flex-1">
          <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
          {isLoading ? (
            <Skeleton className="h-6 w-16 mt-1" />
          ) : (
            <div className="flex items-baseline gap-2">
              <p className="text-xl font-bold text-gray-900 dark:text-gray-100">
                {value}
              </p>
              {change && (
                <span
                  className={cn(
                    'text-xs font-medium',
                    trend === 'warning'
                      ? 'text-amber-600'
                      : trend === 'down'
                      ? 'text-red-600'
                      : 'text-gray-500'
                  )}
                >
                  {change}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function calculateStats(items: WorkItem[]) {
  const total = items.length;
  const completed = items.filter((i) => i.status === 'Completed').length;
  const inProgress = items.filter((i) => i.status === 'In Progress').length;
  const avgProgress =
    total > 0
      ? Math.round(items.reduce((sum, i) => sum + (i.progress || 0), 0) / total)
      : 0;

  return {
    total,
    completed,
    inProgress,
    completedPct: total > 0 ? Math.round((completed / total) * 100) : 0,
    inProgressPct: total > 0 ? Math.round((inProgress / total) * 100) : 0,
    avgProgress,
  };
}

// Grid View Component
interface WorkItemsGridProps {
  data: WorkItem[];
  isLoading?: boolean;
  onItemClick?: (item: WorkItem) => void;
}

function WorkItemsGrid({ data, isLoading, onItemClick }: WorkItemsGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Card key={i} className="p-4">
            <Skeleton className="h-4 w-3/4 mb-2" />
            <Skeleton className="h-3 w-1/2 mb-4" />
            <Skeleton className="h-2 w-full mb-2" />
            <Skeleton className="h-3 w-1/4" />
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {data.map((item) => (
        <motion.div
          key={item.task_code}
          layoutId={item.task_code}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <Card
            hover
            className="p-4 cursor-pointer"
            onClick={() => onItemClick?.(item)}
          >
            <div className="flex items-start justify-between mb-2">
              <span className="text-xs font-mono text-gray-500">
                {item.task_code}
              </span>
              <Badge
                variant={
                  item.status === 'Completed'
                    ? 'success'
                    : item.status === 'In Progress'
                    ? 'primary'
                    : 'secondary'
                }
                size="sm"
              >
                {item.status}
              </Badge>
            </div>
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-1 line-clamp-2">
              {item.name}
            </h3>
            {item.wbs && (
              <p className="text-xs text-gray-500 mb-3">{item.wbs}</p>
            )}
            <div className="mt-3">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Progress</span>
                <span>{item.progress || 0}%</span>
              </div>
              <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${item.progress || 0}%` }}
                  transition={{ duration: 0.5 }}
                  className={cn(
                    'h-full rounded-full',
                    item.progress === 100
                      ? 'bg-green-500'
                      : item.progress && item.progress >= 50
                      ? 'bg-blue-500'
                      : 'bg-amber-500'
                  )}
                />
              </div>
            </div>
            {item.assigned_resources && item.assigned_resources.length > 0 && (
              <div className="flex -space-x-2 mt-3">
                {item.assigned_resources.slice(0, 3).map((r, i) => (
                  <div
                    key={i}
                    className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-medium ring-2 ring-white dark:ring-gray-800"
                  >
                    {r.charAt(0)}
                  </div>
                ))}
                {item.assigned_resources.length > 3 && (
                  <div className="w-6 h-6 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-xs text-gray-600 ring-2 ring-white dark:ring-gray-800">
                    +{item.assigned_resources.length - 3}
                  </div>
                )}
              </div>
            )}
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

// Coming Soon Placeholder
function ComingSoon({ feature }: { feature: string }) {
  return (
    <div className="text-center">
      <div className="w-24 h-24 mx-auto mb-4 bg-gradient-to-br from-blue-500/10 to-purple-500/10 rounded-full flex items-center justify-center">
        <Layers className="w-12 h-12 text-blue-500" />
      </div>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
        {feature}
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        This feature is coming soon. Stay tuned!
      </p>
    </div>
  );
}

// Work Item Detail Drawer
interface WorkItemDrawerProps {
  item: WorkItem;
  onClose: () => void;
}

function WorkItemDrawer({ item, onClose }: WorkItemDrawerProps) {
  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/30 z-40"
        onClick={onClose}
      />

      {/* Drawer */}
      <motion.div
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
        className="fixed right-0 top-0 h-full w-[480px] bg-white dark:bg-gray-900 shadow-2xl z-50 overflow-y-auto"
      >
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4 flex items-center justify-between">
          <div>
            <span className="text-xs font-mono text-gray-500">{item.task_code}</span>
            <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {item.name}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Status & Progress */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                Status
              </label>
              <Badge
                variant={
                  item.status === 'Completed'
                    ? 'success'
                    : item.status === 'In Progress'
                    ? 'primary'
                    : 'secondary'
                }
                className="mt-1"
              >
                {item.status}
              </Badge>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                Progress
              </label>
              <div className="mt-2">
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium">{item.progress || 0}%</span>
                </div>
                <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full"
                    style={{ width: `${item.progress || 0}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Baseline Dates
              </h3>
              <div>
                <label className="text-xs text-gray-500">Start</label>
                <p className="text-sm font-medium">{item.planned_start || '-'}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500">End</label>
                <p className="text-sm font-medium">{item.planned_end || '-'}</p>
              </div>
            </div>
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Current Dates
              </h3>
              <div>
                <label className="text-xs text-gray-500">Start</label>
                <p className="text-sm font-medium">{item.current_start || '-'}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500">End</label>
                <p className="text-sm font-medium">{item.current_end || '-'}</p>
              </div>
            </div>
          </div>

          {/* Hierarchy */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
              Hierarchy
            </h3>
            <div className="space-y-2 text-sm">
              {item.program && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Program</span>
                  <span className="font-medium">{item.program}</span>
                </div>
              )}
              {item.project && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Project</span>
                  <span className="font-medium">{item.project}</span>
                </div>
              )}
              {item.phase && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Phase</span>
                  <span className="font-medium">{item.phase}</span>
                </div>
              )}
              {item.wbs && (
                <div className="flex justify-between">
                  <span className="text-gray-500">WBS</span>
                  <span className="font-medium">{item.wbs}</span>
                </div>
              )}
            </div>
          </div>

          {/* Attributes */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
              Attributes
            </h3>
            <div className="flex flex-wrap gap-2">
              {item.priority && (
                <Badge variant="warning" size="sm">
                  {item.priority} Priority
                </Badge>
              )}
              {item.complexity && (
                <Badge variant="secondary" size="sm">
                  {item.complexity} Complexity
                </Badge>
              )}
            </div>
          </div>

          {/* Resources */}
          {item.assigned_resources && item.assigned_resources.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Assigned Resources
              </h3>
              <div className="flex flex-wrap gap-2">
                {item.assigned_resources.map((resource, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 bg-gray-100 dark:bg-gray-800 rounded-full px-3 py-1"
                  >
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-medium">
                      {resource.charAt(0)}
                    </div>
                    <span className="text-sm">{resource}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </>
  );
}
