/**
 * Mini Gantt Bar component for table cells
 * Shows baseline vs current date visualization
 */
import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { cn, calculateGanttBar } from '../../lib/utils';

interface MiniGanttBarProps {
  plannedStart: string;
  plannedEnd: string;
  currentStart: string;
  currentEnd: string;
  rangeStart: Date;
  rangeEnd: Date;
  status: string;
  showTooltip?: boolean;
}

export function MiniGanttBar({
  plannedStart,
  plannedEnd,
  currentStart,
  currentEnd,
  rangeStart,
  rangeEnd,
  status,
}: MiniGanttBarProps) {
  // Calculate bar positions
  const baseline = useMemo(
    () => calculateGanttBar(plannedStart, plannedEnd, rangeStart, rangeEnd),
    [plannedStart, plannedEnd, rangeStart, rangeEnd]
  );

  const current = useMemo(
    () => calculateGanttBar(currentStart, currentEnd, rangeStart, rangeEnd),
    [currentStart, currentEnd, rangeStart, rangeEnd]
  );

  // Determine color based on status and delay
  const isDelayed = new Date(currentEnd) > new Date(plannedEnd);
  
  const statusColors: Record<string, string> = {
    'Completed': 'bg-green-500',
    'In Progress': isDelayed ? 'bg-amber-500' : 'bg-blue-500',
    'Not Started': 'bg-gray-400',
    'On Hold': 'bg-amber-500',
    'Cancelled': 'bg-red-400',
  };

  return (
    <div className="relative h-8 w-full min-w-[120px]">
      {/* Background grid */}
      <div className="absolute inset-0 flex">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="flex-1 border-r border-gray-100 dark:border-gray-800 last:border-r-0"
          />
        ))}
      </div>

      {/* Baseline bar (lighter, behind) */}
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${baseline.width}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="absolute top-1 h-2.5 rounded-full bg-gray-200 dark:bg-gray-700"
        style={{ left: `${baseline.left}%` }}
        title={`Baseline: ${plannedStart} - ${plannedEnd}`}
      />

      {/* Current bar (colored, in front) */}
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${current.width}%` }}
        transition={{ duration: 0.5, ease: 'easeOut', delay: 0.1 }}
        className={cn(
          'absolute top-4 h-2.5 rounded-full shadow-sm',
          statusColors[status] || 'bg-gray-400'
        )}
        style={{ left: `${current.left}%` }}
        title={`Current: ${currentStart} - ${currentEnd}`}
      />

      {/* Delay indicator */}
      {isDelayed && status !== 'Cancelled' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="absolute right-0 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-red-500"
          title="Delayed"
        />
      )}
    </div>
  );
}

// Legend component for the Gantt bars
export function MiniGanttLegend() {
  return (
    <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
      <div className="flex items-center gap-1.5">
        <div className="w-8 h-2 rounded-full bg-gray-200 dark:bg-gray-700" />
        <span>Baseline</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-8 h-2 rounded-full bg-blue-500" />
        <span>Current</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full bg-red-500" />
        <span>Delayed</span>
      </div>
    </div>
  );
}
