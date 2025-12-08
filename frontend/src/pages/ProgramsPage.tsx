/**
 * Programs Page
 * View and manage programs from the database - NO MOCK DATA
 */
import { useState } from 'react';
import {
  FolderKanban,
  Search,
  Calendar,
  Users,
  TrendingUp,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Progress';
import { cn } from '../lib/utils';
import { usePrograms } from '../lib/queries';
import type { Program } from '../types';

export function ProgramsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  
  const { data, isLoading, isError, error, refetch } = usePrograms();
  
  const programs = data?.data || [];
  
  const filteredPrograms = programs.filter((p) =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.external_id?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Programs
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {programs.length > 0 
              ? `${programs.length} program${programs.length !== 1 ? 's' : ''} in the system`
              : 'No programs yet - import an Excel file to get started'
            }
          </p>
        </div>
        <Button onClick={() => refetch()} variant="outline">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Search */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search programs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Programs Grid */}
      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-64 rounded-xl" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-64 text-red-500">
            <AlertCircle className="w-12 h-12 mb-4" />
            <p className="text-lg font-medium">Failed to load programs</p>
            <p className="text-sm text-gray-500">{error?.message || 'Unknown error'}</p>
            <Button onClick={() => refetch()} className="mt-4" variant="outline">
              Try Again
            </Button>
          </div>
        ) : filteredPrograms.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <FolderKanban className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">
              {searchQuery ? 'No programs match your search' : 'No programs found'}
            </p>
            <p className="text-sm">
              {searchQuery 
                ? 'Try a different search term'
                : 'Import an Excel file to create programs'
              }
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredPrograms.map((program) => (
              <ProgramCard key={program.id} program={program} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface ProgramCardProps {
  program: Program & {
    project_count?: number;
    work_item_count?: number;
    progress?: number;
  };
}

function ProgramCard({ program }: ProgramCardProps) {
  const progress = program.progress ?? 0;
  const projectCount = program.project_count ?? 0;
  const workItemCount = program.work_item_count ?? 0;
  
  return (
    <Card hover className="p-5">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center">
            <FolderKanban className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              {program.name}
            </h3>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">{program.external_id}</span>
              <Badge
                variant={program.status === 'Active' ? 'success' : program.status === 'Completed' ? 'default' : 'warning'}
                size="sm"
              >
                {program.status}
              </Badge>
            </div>
          </div>
        </div>
      </div>

      {/* Description */}
      {program.description && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 line-clamp-2">
          {program.description}
        </p>
      )}

      {/* Progress */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm text-gray-500">Completion</span>
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {progress}%
          </span>
        </div>
        <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-500',
              progress >= 75
                ? 'bg-green-500'
                : progress >= 50
                ? 'bg-blue-500'
                : progress > 0
                ? 'bg-amber-500'
                : 'bg-gray-300'
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <div className="text-center">
          <Calendar className="w-4 h-4 mx-auto mb-1 text-gray-400" />
          <p className="text-xs text-gray-500">Timeline</p>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {program.baseline_start_date && program.baseline_end_date
              ? `${new Date(program.baseline_start_date).toLocaleDateString('en-US', { month: 'short' })} - ${new Date(program.baseline_end_date).toLocaleDateString('en-US', { month: 'short' })}`
              : '-'
            }
          </p>
        </div>
        <div className="text-center">
          <TrendingUp className="w-4 h-4 mx-auto mb-1 text-gray-400" />
          <p className="text-xs text-gray-500">Projects</p>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {projectCount}
          </p>
        </div>
        <div className="text-center">
          <Users className="w-4 h-4 mx-auto mb-1 text-gray-400" />
          <p className="text-xs text-gray-500">Tasks</p>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {workItemCount}
          </p>
        </div>
      </div>

      {/* Owner & Priority */}
      {(program.program_owner || program.priority) && (
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
          {program.program_owner && (
            <span className="text-xs text-gray-500">
              Owner: <span className="font-medium text-gray-700 dark:text-gray-300">{program.program_owner}</span>
            </span>
          )}
          {program.priority && (
            <Badge variant={program.priority >= 4 ? 'danger' : program.priority >= 3 ? 'warning' : 'default'} size="sm">
              P{program.priority}
            </Badge>
          )}
        </div>
      )}
    </Card>
  );
}
