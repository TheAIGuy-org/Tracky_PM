/**
 * Flagged Items Page
 * View and resolve flagged work items - NO MOCK DATA
 */
import { useState } from 'react';
import {
  AlertTriangle,
  Search,
  CheckCircle,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Progress';
import { usePrograms, useFlaggedItems, useResolveFlaggedItem } from '../lib/queries';

export function FlaggedItemsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProgramId, setSelectedProgramId] = useState<string>('');
  
  // Get programs for dropdown
  const { data: programsData } = usePrograms();
  const programs = programsData?.data || [];
  
  // Get flagged items for selected program
  const { 
    data: flaggedData, 
    isLoading, 
    isError, 
    error,
    refetch 
  } = useFlaggedItems(selectedProgramId, {
    enabled: !!selectedProgramId,
  });
  
  const flaggedItems = flaggedData?.items || [];
  
  // Resolve mutation
  const resolveMutation = useResolveFlaggedItem();

  const filteredItems = flaggedItems.filter(
    (item) =>
      item.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.external_id?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleResolve = (workItemId: string, newStatus: string) => {
    resolveMutation.mutate(
      { workItemId, newStatus, resolutionNote: `Resolved via UI: set to ${newStatus}` },
      { onSuccess: () => refetch() }
    );
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Flagged Items
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Work items removed from Excel that were in progress - require PM decision
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selectedProgramId && flaggedItems.length > 0 && (
            <Badge variant="warning" size="lg">
              {flaggedItems.length} item{flaggedItems.length !== 1 ? 's' : ''} need review
            </Badge>
          )}
          <Button onClick={() => refetch()} variant="outline" disabled={!selectedProgramId}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Program Selector */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center gap-4">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Select Program:
        </label>
        <select
          value={selectedProgramId}
          onChange={(e) => setSelectedProgramId(e.target.value)}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        >
          <option value="">-- Select a program --</option>
          {programs.map((p) => (
            <option key={p.id} value={p.id}>
              {p.external_id} - {p.name}
            </option>
          ))}
        </select>
        
        {selectedProgramId && (
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search flagged items..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
          </div>
        )}
      </div>

      {/* Flagged Items List */}
      <div className="flex-1 overflow-auto p-6">
        {!selectedProgramId ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <AlertTriangle className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">Select a program</p>
            <p className="text-sm">Choose a program to view flagged items</p>
          </div>
        ) : isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-64 text-red-500">
            <AlertCircle className="w-12 h-12 mb-4" />
            <p className="text-lg font-medium">Failed to load flagged items</p>
            <p className="text-sm text-gray-500">{error?.message || 'Unknown error'}</p>
            <Button onClick={() => refetch()} className="mt-4" variant="outline">
              Try Again
            </Button>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <CheckCircle className="w-12 h-12 mb-4 text-green-400" />
            <p className="text-lg font-medium">All clear!</p>
            <p className="text-sm">No flagged items for this program</p>
          </div>
        ) : (
          <div className="space-y-4 max-w-4xl">
            {filteredItems.map((item) => (
              <FlaggedItemCard 
                key={item.id} 
                item={item} 
                onResolve={handleResolve}
                isResolving={resolveMutation.isPending}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface FlaggedItem {
  id: string;
  external_id: string;
  name?: string;
  status?: string;
  review_message?: string;
  completion_percent?: number;
}

interface FlaggedItemCardProps {
  item: FlaggedItem;
  onResolve: (workItemId: string, newStatus: string) => void;
  isResolving: boolean;
}

function FlaggedItemCard({ item, onResolve, isResolving }: FlaggedItemCardProps) {
  return (
    <Card className="p-4">
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center flex-shrink-0">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-sm text-gray-500">{item.external_id}</span>
            <Badge
              variant={
                item.status === 'In Progress'
                  ? 'info'
                  : item.status === 'On Hold'
                  ? 'warning'
                  : 'default'
              }
              size="sm"
            >
              {item.status || 'Unknown'}
            </Badge>
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
            {item.name || 'Unnamed Work Item'}
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {item.review_message || 'Flagged for PM review'}
          </p>
          
          {/* Completion */}
          {item.completion_percent !== undefined && (
            <div className="mt-2 flex items-center gap-2">
              <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full max-w-32">
                <div 
                  className="h-full bg-blue-500 rounded-full" 
                  style={{ width: `${item.completion_percent}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">{item.completion_percent}% complete</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button 
            size="sm" 
            variant="outline"
            onClick={() => onResolve(item.id, 'In Progress')}
            disabled={isResolving}
          >
            Continue
          </Button>
          <Button 
            size="sm" 
            variant="outline"
            onClick={() => onResolve(item.id, 'On Hold')}
            disabled={isResolving}
          >
            Hold
          </Button>
          <Button 
            size="sm" 
            variant="danger"
            onClick={() => onResolve(item.id, 'Cancelled')}
            disabled={isResolving}
          >
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}
