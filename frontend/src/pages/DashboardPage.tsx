/**
 * Dashboard page - Main overview with KPIs and quick actions
 */
import { motion } from 'framer-motion';
import {
  TrendingUp,
  TrendingDown,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Users,
  Upload,
  ArrowRight,
  Target,
  BarChart3,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn, formatNumber, formatRelativeTime } from '../lib/utils';
import { useImportBatches, useResourceUtilization, useDashboardStats } from '../lib/queries';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Spinner, ProgressBar, Skeleton } from '../components/ui/Progress';

// Animation variants for staggered children
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export function DashboardPage() {
  const { data: batches, isLoading: batchesLoading } = useImportBatches();
  const { data: resources, isLoading: resourcesLoading } = useResourceUtilization();
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  
  // Get real stats from backend
  const totalTasks = stats?.work_items?.total || 0;
  const completedTasks = stats?.work_items?.by_status?.['Completed'] || 0;
  const inProgressTasks = stats?.work_items?.by_status?.['In Progress'] || 0;
  const flaggedTasks = stats?.work_items?.flagged || 0;

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="p-6 space-y-6 max-w-7xl mx-auto"
    >
      {/* Hero Section */}
      <motion.div variants={itemVariants}>
        <Card className="relative overflow-hidden bg-gradient-to-br from-blue-600 via-blue-700 to-purple-700">
          <div className="relative z-10 p-6 text-white">
            <h1 className="text-3xl font-bold">Welcome to Tracky PM</h1>
            <p className="mt-2 text-blue-100 max-w-2xl">
              Your intelligent project management command center. Import schedules,
              track progress, and identify issues before they become problems.
            </p>
            <div className="mt-4 flex gap-3">
              <Link to="/work-items">
                <Button className="bg-white text-blue-600 hover:bg-blue-50">
                  <Upload className="h-4 w-4 mr-2" />
                  View Work Items
                </Button>
              </Link>
              <Link to="/resources">
                <Button
                  variant="outline"
                  className="border-white/30 text-white hover:bg-white/10"
                >
                  Manage Resources
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              </Link>
            </div>
          </div>
          {/* Decorative elements */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/3" />
          <div className="absolute bottom-0 right-32 w-32 h-32 bg-white/5 rounded-full translate-y-1/2" />
        </Card>
      </motion.div>

      {/* KPI Cards */}
      <motion.div variants={itemVariants}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            title="Total Tasks"
            value={totalTasks}
            icon={<Target className="h-5 w-5" />}
            color="blue"
            isLoading={statsLoading}
          />
          <KPICard
            title="Completed"
            value={completedTasks}
            icon={<CheckCircle2 className="h-5 w-5" />}
            color="green"
            isLoading={statsLoading}
          />
          <KPICard
            title="In Progress"
            value={inProgressTasks}
            icon={<Clock className="h-5 w-5" />}
            color="amber"
            isLoading={statsLoading}
          />
          <KPICard
            title="Flagged for Review"
            value={flaggedTasks}
            icon={<AlertTriangle className="h-5 w-5" />}
            color="red"
            link="/flagged"
            isLoading={statsLoading}
          />
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Imports */}
        <motion.div variants={itemVariants} className="lg:col-span-2">
          <Card className="p-0">
            <div className="p-4 border-b border-gray-200 dark:border-gray-800">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Recent Imports
                </h2>
                <Link
                  to="/audit"
                  className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  View All
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
            <div className="p-4">
              {batchesLoading ? (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              ) : batches?.batches?.length ? (
                <div className="space-y-3">
                  {batches.batches.slice(0, 5).map((batch: any) => (
                    <div
                      key={batch.id}
                      className="flex items-center gap-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <div
                        className={cn(
                          'p-2 rounded-lg',
                          batch.status === 'completed'
                            ? 'bg-green-100 dark:bg-green-900/30'
                            : batch.status === 'failed'
                            ? 'bg-red-100 dark:bg-red-900/30'
                            : 'bg-blue-100 dark:bg-blue-900/30'
                        )}
                      >
                        <Upload
                          className={cn(
                            'h-4 w-4',
                            batch.status === 'completed'
                              ? 'text-green-600'
                              : batch.status === 'failed'
                              ? 'text-red-600'
                              : 'text-blue-600'
                          )}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {batch.file_name || 'Import Batch'}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {formatRelativeTime(batch.started_at)}
                        </p>
                      </div>
                      <div className="text-right">
                        <Badge
                          variant={
                            batch.status === 'completed'
                              ? 'success'
                              : batch.status === 'failed'
                              ? 'danger'
                              : 'primary'
                          }
                        >
                          {batch.status}
                        </Badge>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {formatNumber(batch.items_processed || 0)} items
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={<Upload className="h-8 w-8" />}
                  title="No imports yet"
                  description="Import your first Excel file to get started"
                />
              )}
            </div>
          </Card>
        </motion.div>

        {/* Resource Utilization */}
        <motion.div variants={itemVariants}>
          <Card className="p-0">
            <div className="p-4 border-b border-gray-200 dark:border-gray-800">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Resource Utilization
                </h2>
                <Link
                  to="/resources"
                  className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  View All
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
            <div className="p-4">
              {resourcesLoading ? (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              ) : resources ? (
                <div className="space-y-4">
                  {/* Summary */}
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {resources.total_resources || 0}
                      </p>
                      <p className="text-xs text-gray-500">Total</p>
                    </div>
                    <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20">
                      <p className="text-lg font-semibold text-amber-600">
                        {resources.at_risk_count || 0}
                      </p>
                      <p className="text-xs text-gray-500">At Risk</p>
                    </div>
                    <div className="p-2 rounded-lg bg-red-50 dark:bg-red-900/20">
                      <p className="text-lg font-semibold text-red-600">
                        {resources.over_allocated_count || 0}
                      </p>
                      <p className="text-xs text-gray-500">Over</p>
                    </div>
                  </div>

                  {/* Resource bars */}
                  {resources.all_resources?.slice(0, 4).map((resource: any) => {
                    // Calculate utilization - handle different field names from backend
                    const utilization = resource.utilization_percent ?? 
                      (resource.total_allocation != null && resource.max_utilization 
                        ? Math.round((resource.total_allocation / resource.max_utilization) * 100) 
                        : 0);
                    const displayName = resource.name || resource.resource_id || resource.external_id || 'Unknown';
                    
                    return (
                    <div key={resource.id || resource.resource_id} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600 dark:text-gray-400 truncate">
                          {displayName}
                        </span>
                        <span
                          className={cn(
                            'font-medium',
                            utilization > 100
                              ? 'text-red-600'
                              : utilization > 80
                              ? 'text-amber-600'
                              : 'text-green-600'
                          )}
                        >
                          {utilization}%
                        </span>
                      </div>
                      <ProgressBar
                        value={Math.min(utilization || 0, 100)}
                        max={100}
                        variant={
                          utilization > 100
                            ? 'danger'
                            : utilization > 80
                            ? 'warning'
                            : 'success'
                        }
                      />
                    </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  icon={<Users className="h-8 w-8" />}
                  title="No resources"
                  description="Import a schedule to see resource utilization"
                />
              )}
            </div>
          </Card>
        </motion.div>
      </div>

      {/* Quick Actions */}
      <motion.div variants={itemVariants}>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <QuickActionCard
            icon={<Upload className="h-6 w-6" />}
            title="Import Schedule"
            description="Upload an Excel file to import work items"
            to="/work-items"
          />
          <QuickActionCard
            icon={<Users className="h-6 w-6" />}
            title="Manage Resources"
            description="View and manage resource allocation"
            to="/resources"
          />
          <QuickActionCard
            icon={<BarChart3 className="h-6 w-6" />}
            title="View Analytics"
            description="Analyze project metrics and trends"
            to="/audit"
          />
        </div>
      </motion.div>
    </motion.div>
  );
}

// KPI Card Component
interface KPICardProps {
  title: string;
  value: number;
  change?: number;
  changeLabel?: string;
  icon: React.ReactNode;
  color: 'blue' | 'green' | 'amber' | 'red';
  link?: string;
  isLoading?: boolean;
}

function KPICard({ title, value, change, changeLabel, icon, color, link, isLoading }: KPICardProps) {
  const colorClasses = {
    blue: 'bg-blue-100 text-blue-600 dark:bg-blue-900/30',
    green: 'bg-green-100 text-green-600 dark:bg-green-900/30',
    amber: 'bg-amber-100 text-amber-600 dark:bg-amber-900/30',
    red: 'bg-red-100 text-red-600 dark:bg-red-900/30',
  };

  const content = (
    <Card className={cn('p-4', link && 'cursor-pointer hover:shadow-md transition-shadow')}>
      <div className="flex items-start justify-between">
        <div className={cn('p-2 rounded-lg', colorClasses[color])}>
          {icon}
        </div>
        {change !== undefined && (
          <div
            className={cn(
              'flex items-center gap-1 text-sm font-medium',
              change >= 0 ? 'text-green-600' : 'text-red-600'
            )}
          >
            {change >= 0 ? (
              <TrendingUp className="h-4 w-4" />
            ) : (
              <TrendingDown className="h-4 w-4" />
            )}
            {Math.abs(change)}%
          </div>
        )}
      </div>
      <div className="mt-3">
        {isLoading ? (
          <Skeleton className="h-8 w-20 rounded" />
        ) : (
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatNumber(value)}
          </p>
        )}
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {title}
          {changeLabel && (
            <span className="ml-1 text-gray-400">({changeLabel})</span>
          )}
        </p>
      </div>
    </Card>
  );

  if (link) {
    return <Link to={link}>{content}</Link>;
  }

  return content;
}

// Quick Action Card Component
interface QuickActionCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  to: string;
}

function QuickActionCard({ icon, title, description, to }: QuickActionCardProps) {
  return (
    <Link to={to}>
      <Card className="p-4 cursor-pointer hover:shadow-md transition-all hover:border-blue-200 dark:hover:border-blue-800 group">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 group-hover:bg-blue-100 group-hover:text-blue-600 dark:group-hover:bg-blue-900/30 dark:group-hover:text-blue-400 transition-colors">
            {icon}
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
              {title}
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {description}
            </p>
          </div>
        </div>
      </Card>
    </Link>
  );
}

// Empty State Component
interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
}

function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <div className="p-3 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-400 mb-3">
        {icon}
      </div>
      <p className="font-medium text-gray-900 dark:text-white">{title}</p>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{description}</p>
    </div>
  );
}
