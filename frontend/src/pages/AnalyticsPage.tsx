/**
 * Analytics Page
 * System analytics and metrics from real data - NO MOCK DATA
 */
import {
  BarChart3,
  RefreshCw,
  AlertCircle,
  TrendingUp,
  FileSpreadsheet,
  Users,
  CheckCircle,
  Clock,
  AlertTriangle,
  XCircle,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Skeleton } from '../components/ui/Progress';
import { useDashboardStats, useImportBatches, useResourceUtilization } from '../lib/queries';

export function AnalyticsPage() {
  const { data: stats, isLoading: statsLoading, isError: statsError, refetch: refetchStats } = useDashboardStats();
  const { data: imports, isLoading: importsLoading } = useImportBatches(undefined, 20);
  const { data: utilization, isLoading: utilizationLoading } = useResourceUtilization();
  
  const isLoading = statsLoading || importsLoading || utilizationLoading;
  
  // Calculate work item status percentages
  const statusCounts = stats?.work_items?.by_status || {};
  const totalWorkItems = stats?.work_items?.total || 0;
  
  // Import statistics
  const importBatches = imports?.batches || [];
  const successfulImports = importBatches.filter(b => b.status === 'completed').length;
  const failedImports = importBatches.filter(b => b.status === 'failed').length;
  
  // Resource metrics
  const overAllocated = utilization?.over_allocated_count || 0;
  const atRisk = utilization?.at_risk_count || 0;
  const totalResources = utilization?.total_resources || 0;

  const handleRefresh = () => {
    refetchStats();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Analytics
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            System metrics and performance insights from real-time data
          </p>
        </div>
        <Button onClick={handleRefresh} variant="outline">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6">
        {statsError ? (
          <div className="flex flex-col items-center justify-center h-64 text-red-500">
            <AlertCircle className="w-12 h-12 mb-4" />
            <p className="text-lg font-medium">Failed to load analytics</p>
            <Button onClick={handleRefresh} className="mt-4" variant="outline">
              Try Again
            </Button>
          </div>
        ) : (
          <div className="space-y-6 max-w-6xl">
            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard
                title="Total Programs"
                value={stats?.programs?.total ?? 0}
                icon={BarChart3}
                color="brand"
                isLoading={isLoading}
              />
              <MetricCard
                title="Work Items"
                value={totalWorkItems}
                icon={TrendingUp}
                color="blue"
                isLoading={isLoading}
              />
              <MetricCard
                title="Resources"
                value={totalResources}
                icon={Users}
                color="purple"
                isLoading={isLoading}
              />
              <MetricCard
                title="Flagged Items"
                value={stats?.work_items?.flagged ?? 0}
                icon={AlertTriangle}
                color="amber"
                isLoading={isLoading}
              />
            </div>

            {/* Work Item Status Breakdown */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Work Item Status Distribution
              </h2>
              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Skeleton key={i} className="h-8 rounded" />
                  ))}
                </div>
              ) : totalWorkItems === 0 ? (
                <p className="text-gray-500 text-center py-8">
                  No work items in the system yet
                </p>
              ) : (
                <div className="space-y-3">
                  <StatusBar 
                    label="Not Started" 
                    count={statusCounts['Not Started'] || 0} 
                    total={totalWorkItems}
                    color="bg-gray-400"
                    icon={Clock}
                  />
                  <StatusBar 
                    label="In Progress" 
                    count={statusCounts['In Progress'] || 0} 
                    total={totalWorkItems}
                    color="bg-blue-500"
                    icon={TrendingUp}
                  />
                  <StatusBar 
                    label="Completed" 
                    count={statusCounts['Completed'] || 0} 
                    total={totalWorkItems}
                    color="bg-green-500"
                    icon={CheckCircle}
                  />
                  <StatusBar 
                    label="On Hold" 
                    count={statusCounts['On Hold'] || 0} 
                    total={totalWorkItems}
                    color="bg-amber-500"
                    icon={AlertTriangle}
                  />
                  <StatusBar 
                    label="Cancelled" 
                    count={statusCounts['Cancelled'] || 0} 
                    total={totalWorkItems}
                    color="bg-red-500"
                    icon={XCircle}
                  />
                </div>
              )}
            </Card>

            {/* Two column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Import Statistics */}
              <Card className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                  Import Statistics
                </h2>
                {isLoading ? (
                  <Skeleton className="h-32 rounded" />
                ) : importBatches.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">
                    No imports have been performed yet
                  </p>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600 dark:text-gray-400">Total Imports</span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {importBatches.length}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600 dark:text-gray-400">Successful</span>
                      <span className="font-semibold text-green-600">
                        {successfulImports}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600 dark:text-gray-400">Failed</span>
                      <span className="font-semibold text-red-600">
                        {failedImports}
                      </span>
                    </div>
                    <div className="pt-4 border-t border-gray-100 dark:border-gray-800">
                      <div className="text-sm text-gray-500">
                        Last import: {importBatches[0]?.file_name || 'N/A'}
                      </div>
                    </div>
                  </div>
                )}
              </Card>

              {/* Resource Utilization */}
              <Card className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                  Resource Utilization
                </h2>
                {isLoading ? (
                  <Skeleton className="h-32 rounded" />
                ) : totalResources === 0 ? (
                  <p className="text-gray-500 text-center py-8">
                    No resources in the system yet
                  </p>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600 dark:text-gray-400">Total Resources</span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {totalResources}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600 dark:text-gray-400">Over-Allocated</span>
                      <span className={`font-semibold ${overAllocated > 0 ? 'text-red-600' : 'text-gray-500'}`}>
                        {overAllocated}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600 dark:text-gray-400">At Risk (80%+)</span>
                      <span className={`font-semibold ${atRisk > 0 ? 'text-amber-600' : 'text-gray-500'}`}>
                        {atRisk}
                      </span>
                    </div>
                    <div className="pt-4 border-t border-gray-100 dark:border-gray-800">
                      <div className="text-sm text-gray-500">
                        Health: {overAllocated === 0 && atRisk === 0 
                          ? '✅ All resources balanced' 
                          : overAllocated > 0 
                            ? '⚠️ Needs attention'
                            : '⚡ Monitor closely'
                        }
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            </div>

            {/* Recent Imports Timeline */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Recent Import Activity
              </h2>
              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-12 rounded" />
                  ))}
                </div>
              ) : importBatches.length === 0 ? (
                <p className="text-gray-500 text-center py-8">
                  Import an Excel file to see activity here
                </p>
              ) : (
                <div className="space-y-3">
                  {importBatches.slice(0, 5).map((batch) => (
                    <div 
                      key={batch.id} 
                      className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50"
                    >
                      <FileSpreadsheet className="w-5 h-5 text-gray-400" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                          {batch.file_name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {new Date(batch.started_at).toLocaleString()}
                        </p>
                      </div>
                      <span className={`text-xs font-medium px-2 py-1 rounded ${
                        batch.status === 'completed' 
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                          : batch.status === 'failed'
                            ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                            : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                      }`}>
                        {batch.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

// Helper Components

interface MetricCardProps {
  title: string;
  value: number;
  icon: React.ElementType;
  color: 'brand' | 'blue' | 'purple' | 'amber' | 'green' | 'red';
  isLoading: boolean;
}

function MetricCard({ title, value, icon: Icon, color, isLoading }: MetricCardProps) {
  const colorStyles = {
    brand: 'from-brand-500 to-brand-600',
    blue: 'from-blue-500 to-blue-600',
    purple: 'from-purple-500 to-purple-600',
    amber: 'from-amber-500 to-amber-600',
    green: 'from-green-500 to-green-600',
    red: 'from-red-500 to-red-600',
  };

  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${colorStyles[color]} flex items-center justify-center`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
          {isLoading ? (
            <Skeleton className="h-7 w-16 rounded mt-1" />
          ) : (
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
          )}
        </div>
      </div>
    </Card>
  );
}

interface StatusBarProps {
  label: string;
  count: number;
  total: number;
  color: string;
  icon: React.ElementType;
}

function StatusBar({ label, count, total, color, icon: Icon }: StatusBarProps) {
  const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
  
  return (
    <div className="flex items-center gap-3">
      <Icon className="w-4 h-4 text-gray-400 flex-shrink-0" />
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {count} ({percentage}%)
          </span>
        </div>
        <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div 
            className={`h-full ${color} rounded-full transition-all duration-500`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    </div>
  );
}
