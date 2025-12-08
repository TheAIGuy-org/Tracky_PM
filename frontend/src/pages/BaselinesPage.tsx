/**
 * Baselines Page
 * View baseline versions for scope tracking - NO MOCK DATA
 */
import { useState } from 'react';
import {
  GitBranch,
  RefreshCw,
  AlertCircle,
  Calendar,
  FileText,
  User,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Progress';
import { usePrograms, useBaselineVersions } from '../lib/queries';

export function BaselinesPage() {
  const [selectedProgramId, setSelectedProgramId] = useState<string>('');
  
  // Get programs for dropdown
  const { data: programsData } = usePrograms();
  const programs = programsData?.data || [];
  
  // Get baselines for selected program
  const { 
    data: baselinesData, 
    isLoading, 
    isError, 
    error,
    refetch 
  } = useBaselineVersions(selectedProgramId, {
    enabled: !!selectedProgramId,
  });
  
  const baselines = baselinesData?.versions || [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Baseline Versions
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Track scope changes and baseline snapshots over time
          </p>
        </div>
        <Button onClick={() => refetch()} variant="outline" disabled={!selectedProgramId}>
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Program Selector */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center gap-4">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Select Program:
        </label>
        <select
          value={selectedProgramId}
          onChange={(e) => setSelectedProgramId(e.target.value)}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-brand-500 focus:border-transparent min-w-[300px]"
        >
          <option value="">-- Select a program --</option>
          {programs.map((p) => (
            <option key={p.id} value={p.id}>
              {p.external_id} - {p.name}
            </option>
          ))}
        </select>
        
        {selectedProgramId && baselines.length > 0 && (
          <Badge variant="info" size="lg">
            {baselines.length} baseline version{baselines.length !== 1 ? 's' : ''}
          </Badge>
        )}
      </div>

      {/* Baselines List */}
      <div className="flex-1 overflow-auto p-6">
        {!selectedProgramId ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <GitBranch className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">Select a program</p>
            <p className="text-sm">Choose a program to view baseline history</p>
          </div>
        ) : isLoading ? (
          <div className="space-y-4 max-w-4xl">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-64 text-red-500">
            <AlertCircle className="w-12 h-12 mb-4" />
            <p className="text-lg font-medium">Failed to load baselines</p>
            <p className="text-sm text-gray-500">{error?.message || 'Unknown error'}</p>
            <Button onClick={() => refetch()} className="mt-4" variant="outline">
              Try Again
            </Button>
          </div>
        ) : baselines.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <GitBranch className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">No baseline versions</p>
            <p className="text-sm">Baselines are created automatically during Excel imports</p>
          </div>
        ) : (
          <div className="space-y-4 max-w-4xl">
            {baselines.map((baseline, index) => (
              <BaselineCard 
                key={baseline.id} 
                baseline={baseline} 
                isLatest={index === 0}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface BaselineVersion {
  id: string;
  version_number?: number;
  reason?: string;
  created_by?: string;
  created_at?: string;
  import_batch_id?: string;
  snapshot_data?: unknown;
}

interface BaselineCardProps {
  baseline: BaselineVersion;
  isLatest: boolean;
}

function BaselineCard({ baseline, isLatest }: BaselineCardProps) {
  const createdAt = baseline.created_at 
    ? new Date(baseline.created_at).toLocaleString()
    : 'Unknown';
    
  return (
    <Card className="p-4">
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
          isLatest 
            ? 'bg-green-100 dark:bg-green-900/30' 
            : 'bg-gray-100 dark:bg-gray-800'
        }`}>
          <GitBranch className={`w-5 h-5 ${
            isLatest 
              ? 'text-green-600 dark:text-green-400' 
              : 'text-gray-500'
          }`} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Version {baseline.version_number || '?'}
            </h3>
            {isLatest && (
              <Badge variant="success" size="sm">Latest</Badge>
            )}
          </div>
          
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {baseline.reason || 'No description'}
          </p>

          {/* Meta info */}
          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              <span>{createdAt}</span>
            </div>
            {baseline.created_by && (
              <div className="flex items-center gap-1">
                <User className="w-3 h-3" />
                <span>{baseline.created_by}</span>
              </div>
            )}
            {baseline.import_batch_id && (
              <div className="flex items-center gap-1">
                <FileText className="w-3 h-3" />
                <span>From import batch</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
