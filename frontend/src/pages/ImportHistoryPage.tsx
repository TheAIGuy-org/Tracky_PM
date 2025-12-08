/**
 * Import History Page
 * View past import batches and their results
 */
import { useState } from 'react';
import {
  History,
  Search,
  FileSpreadsheet,
  CheckCircle,
  AlertCircle,
  Clock,
  ChevronRight,
} from 'lucide-react';
import { useImportBatches } from '../lib/queries';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Progress';
import { cn, formatRelativeTime } from '../lib/utils';

export function ImportHistoryPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const { data: batches, isLoading } = useImportBatches();

  const filteredBatches = (batches?.batches || []).filter((batch) =>
    batch.file_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Import History
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          View past imports and their results
        </p>
      </div>

      {/* Search */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search imports..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Import List */}
      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="space-y-4 max-w-4xl">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))}
          </div>
        ) : filteredBatches.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <History className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">No import history</p>
            <p className="text-sm">Your import history will appear here</p>
          </div>
        ) : (
          <div className="space-y-3 max-w-4xl">
            {filteredBatches.map((batch) => (
              <ImportBatchCard key={batch.id} batch={batch} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface ImportBatchCardProps {
  batch: {
    id: string;
    file_name: string;
    status: string;
    started_at: string;
    completed_at?: string;
    items_processed: number;
    items_created: number;
    items_updated: number;
    items_flagged: number;
  };
}

function ImportBatchCard({ batch }: ImportBatchCardProps) {
  const statusConfig = {
    completed: { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-100 dark:bg-green-900/30', variant: 'success' as const },
    failed: { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-100 dark:bg-red-900/30', variant: 'danger' as const },
    processing: { icon: Clock, color: 'text-blue-500', bg: 'bg-blue-100 dark:bg-blue-900/30', variant: 'info' as const },
    pending: { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-100 dark:bg-gray-800', variant: 'default' as const },
  };

  const config = statusConfig[batch.status as keyof typeof statusConfig] || statusConfig.pending;
  const StatusIcon = config.icon;

  return (
    <Card hover className="p-4">
      <div className="flex items-center gap-4">
        {/* File Icon */}
        <div className={cn('w-12 h-12 rounded-lg flex items-center justify-center', config.bg)}>
          <FileSpreadsheet className={cn('w-6 h-6', config.color)} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
              {batch.file_name}
            </h3>
            <Badge variant={config.variant} size="sm">
              <StatusIcon className="w-3 h-3 mr-1" />
              {batch.status}
            </Badge>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span>{formatRelativeTime(batch.started_at)}</span>
            <span>•</span>
            <span>{batch.items_processed} items processed</span>
            {batch.items_created > 0 && (
              <>
                <span>•</span>
                <span className="text-green-600">{batch.items_created} created</span>
              </>
            )}
            {batch.items_updated > 0 && (
              <>
                <span>•</span>
                <span className="text-blue-600">{batch.items_updated} updated</span>
              </>
            )}
            {batch.items_flagged > 0 && (
              <>
                <span>•</span>
                <span className="text-amber-600">{batch.items_flagged} flagged</span>
              </>
            )}
          </div>
        </div>

        {/* Arrow */}
        <ChevronRight className="w-5 h-5 text-gray-400" />
      </div>
    </Card>
  );
}
