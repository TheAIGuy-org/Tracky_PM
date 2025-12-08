/**
 * Resources Page
 * View resource allocation and utilization
 */
import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Users,
  UserCheck,
  UserX,
  AlertTriangle,
  Search,
  BarChart3,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { useResourceUtilization } from '../lib/queries';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Progress';
import { cn, formatPercent } from '../lib/utils';
import type { ResourceUtilization } from '../types';

export function ResourcesPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [utilizationFilter, setUtilizationFilter] = useState<'all' | 'over' | 'under' | 'optimal'>('all');

  const { data: resourceData, isLoading } = useResourceUtilization();

  // Extract the resources array from the response
  const resources = useMemo(() => resourceData?.all_resources || [], [resourceData]);

  // Filter resources
  const filteredResources = useMemo(() => {
    if (!resources || resources.length === 0) return [];
    
    return resources.filter((r: ResourceUtilization) => {
      // Search filter
      const searchText = r.resource_id || r.name || '';
      if (searchQuery && !searchText.toLowerCase().includes(searchQuery.toLowerCase())) {
        return false;
      }
      
      // Utilization filter
      const util = r.utilization_percent || 0;
      if (utilizationFilter === 'over' && util <= 100) return false;
      if (utilizationFilter === 'under' && util >= 80) return false;
      if (utilizationFilter === 'optimal' && (util < 80 || util > 100)) return false;
      
      return true;
    });
  }, [resources, searchQuery, utilizationFilter]);

  // Calculate summary stats
  const stats = useMemo(() => {
    if (!resources || resources.length === 0) {
      return { total: 0, overallocated: 0, underutilized: 0, optimal: 0, avgUtil: 0 };
    }
    
    const overallocated = resources.filter((r: ResourceUtilization) => (r.utilization_percent || 0) > 100).length;
    const underutilized = resources.filter((r: ResourceUtilization) => (r.utilization_percent || 0) < 80).length;
    const optimal = resources.filter((r: ResourceUtilization) => {
      const u = r.utilization_percent || 0;
      return u >= 80 && u <= 100;
    }).length;
    const avgUtil = Math.round(
      resources.reduce((sum: number, r: ResourceUtilization) => sum + (r.utilization_percent || 0), 0) / resources.length
    );
    
    return { total: resources.length, overallocated, underutilized, optimal, avgUtil };
  }, [resources]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Resource Management
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Monitor resource allocation and utilization across projects
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 px-6 py-4 bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-800">
        <SummaryCard
          icon={<Users className="w-5 h-5 text-blue-600" />}
          label="Total Resources"
          value={stats.total}
          isLoading={isLoading}
        />
        <SummaryCard
          icon={<UserCheck className="w-5 h-5 text-green-600" />}
          label="Optimal (80-100%)"
          value={stats.optimal}
          isLoading={isLoading}
        />
        <SummaryCard
          icon={<AlertTriangle className="w-5 h-5 text-red-600" />}
          label="Overallocated"
          value={stats.overallocated}
          trend={stats.overallocated > 0 ? 'warning' : undefined}
          isLoading={isLoading}
        />
        <SummaryCard
          icon={<UserX className="w-5 h-5 text-amber-600" />}
          label="Underutilized"
          value={stats.underutilized}
          isLoading={isLoading}
        />
        <SummaryCard
          icon={<BarChart3 className="w-5 h-5 text-purple-600" />}
          label="Avg Utilization"
          value={`${stats.avgUtil}%`}
          isLoading={isLoading}
        />
      </div>

      {/* Filters */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search resources..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-2 w-64 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Utilization filter */}
          <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {([
              { key: 'all', label: 'All' },
              { key: 'over', label: 'Overallocated' },
              { key: 'under', label: 'Underutilized' },
              { key: 'optimal', label: 'Optimal' },
            ] as const).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setUtilizationFilter(key)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                  utilizationFilter === key
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <span className="text-sm text-gray-500">
          {filteredResources.length} resources
        </span>
      </div>

      {/* Resource Grid */}
      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Card key={i} className="p-4">
                <Skeleton className="h-12 w-12 rounded-full mb-3" />
                <Skeleton className="h-4 w-3/4 mb-2" />
                <Skeleton className="h-3 w-1/2 mb-4" />
                <Skeleton className="h-2 w-full" />
              </Card>
            ))}
          </div>
        ) : filteredResources.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <Users className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">No resources found</p>
            <p className="text-sm">Try adjusting your search or filters</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredResources.map((resource: ResourceUtilization, index: number) => (
              <ResourceCard key={resource.resource_id || resource.id} resource={resource} index={index} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Summary Card Component
interface SummaryCardProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  trend?: 'warning';
  isLoading?: boolean;
}

function SummaryCard({ icon, label, value, trend, isLoading }: SummaryCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
          {icon}
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
          {isLoading ? (
            <Skeleton className="h-6 w-12 mt-1" />
          ) : (
            <p className={cn(
              'text-xl font-bold',
              trend === 'warning' ? 'text-red-600' : 'text-gray-900 dark:text-gray-100'
            )}>
              {value}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// Resource Card Component
interface ResourceCardProps {
  resource: ResourceUtilization;
  index: number;
}

function ResourceCard({ resource, index }: ResourceCardProps) {
  // Calculate utilization - handle different field names from backend
  const res = resource as any; // Backend may return different field names
  const utilization = res.utilization_percent ?? 
    res.total_allocated_percent ?? 
    (res.total_allocation != null && res.max_utilization 
      ? Math.round((res.total_allocation / res.max_utilization) * 100) 
      : 0);
  const isOverallocated = utilization > 100;
  const isUnderutilized = utilization < 80;
  const isOptimal = utilization >= 80 && utilization <= 100;

  // Generate avatar color based on name
  const avatarColors = [
    'from-blue-500 to-cyan-500',
    'from-purple-500 to-pink-500',
    'from-green-500 to-teal-500',
    'from-orange-500 to-amber-500',
    'from-red-500 to-rose-500',
    'from-indigo-500 to-violet-500',
  ];
  
  // Use resource_id, external_id, name, or id as display identifier
  const displayId = resource.resource_id || resource.external_id || resource.name || resource.id || 'Unknown';
  const colorIndex = displayId.charCodeAt(0) % avatarColors.length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card hover className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'w-12 h-12 rounded-full flex items-center justify-center text-white text-lg font-bold bg-gradient-to-br',
                avatarColors[colorIndex]
              )}
            >
              {displayId.substring(0, 2).toUpperCase()}
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                {resource.name || displayId}
              </h3>
              <p className="text-xs text-gray-500">
                {resource.assigned_tasks ?? resource.active_tasks ?? 0} tasks assigned
              </p>
            </div>
          </div>
          
          {isOverallocated && (
            <Badge variant="danger" size="sm">
              <AlertTriangle className="w-3 h-3 mr-1" />
              Over
            </Badge>
          )}
          {isUnderutilized && (
            <Badge variant="warning" size="sm">
              <TrendingDown className="w-3 h-3 mr-1" />
              Low
            </Badge>
          )}
          {isOptimal && (
            <Badge variant="success" size="sm">
              <TrendingUp className="w-3 h-3 mr-1" />
              Good
            </Badge>
          )}
        </div>

        {/* Utilization Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Utilization</span>
            <span className={cn(
              'font-semibold',
              isOverallocated ? 'text-red-600' : isUnderutilized ? 'text-amber-600' : 'text-green-600'
            )}>
              {formatPercent(utilization)}
            </span>
          </div>
          
          <div className="relative h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            {/* Optimal zone indicator */}
            <div className="absolute inset-y-0 left-[80%] right-0 bg-green-100 dark:bg-green-900/30" />
            
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(utilization, 150)}%` }}
              transition={{ duration: 0.5, delay: index * 0.05 }}
              className={cn(
                'h-full rounded-full relative',
                isOverallocated
                  ? 'bg-gradient-to-r from-red-400 to-red-600'
                  : isUnderutilized
                  ? 'bg-gradient-to-r from-amber-400 to-amber-600'
                  : 'bg-gradient-to-r from-green-400 to-green-600'
              )}
            />
            
            {/* 100% marker */}
            <div className="absolute top-0 bottom-0 left-[100%] w-0.5 bg-gray-400 dark:bg-gray-500" />
          </div>

          {/* Capacity info */}
          <div className="flex justify-between text-xs text-gray-500">
            <span>0%</span>
            <span className="text-gray-400">|80%</span>
            <span>100%</span>
          </div>
        </div>

        {/* Additional Stats */}
        <div className="grid grid-cols-2 gap-2 mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
          <div className="text-center">
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {res.active_task_count ?? res.active_tasks ?? res.assigned_tasks ?? 0}
            </p>
            <p className="text-xs text-gray-500">Active Tasks</p>
          </div>
          <div className="text-center">
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {res.available_percent ?? res.available_hours ?? (100 - utilization)}%
            </p>
            <p className="text-xs text-gray-500">Available</p>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
