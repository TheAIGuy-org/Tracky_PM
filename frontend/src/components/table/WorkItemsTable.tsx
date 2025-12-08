/**
 * Work Items Super Table with TanStack Table + Virtualization
 * Handles 5000+ rows with smooth performance
 */
import { useMemo, useState, useCallback, useRef } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type VisibilityState,
  type RowSelectionState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Filter,
  Columns,
  Download,
  RefreshCw,
  Search,
  ChevronDown,
  X,
  Eye,
  EyeOff,
} from 'lucide-react';
import type { WorkItem } from '../../types';
import { cn, formatDate, formatPercent, truncate, isDelayed } from '../../lib/utils';
import { Button } from '../ui/Button';
import { Badge, StatusBadge, PriorityBadge, ComplexityBadge } from '../ui/Badge';
import { MiniGanttBar } from './MiniGanttBar';
import { useSelectionStore } from '../../stores';

interface WorkItemsTableProps {
  data: WorkItem[];
  isLoading?: boolean;
  onRowClick?: (item: WorkItem) => void;
  onRefresh?: () => void;
}

// Column definitions
function useColumns(rangeStart: Date, rangeEnd: Date): ColumnDef<WorkItem>[] {
  return useMemo(
    () => [
      {
        id: 'select',
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            aria-label="Select row"
          />
        ),
        size: 40,
        enableSorting: false,
        enableHiding: false,
      },
      {
        accessorKey: 'task_code',
        header: 'Task Code',
        cell: ({ row }) => (
          <span className="font-mono text-xs text-gray-600 dark:text-gray-400">
            {row.original.task_code}
          </span>
        ),
        size: 100,
      },
      {
        accessorKey: 'name',
        header: 'Name',
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {truncate(row.original.name, 40)}
            </span>
            {row.original.wbs && (
              <span className="text-xs text-gray-500">{row.original.wbs}</span>
            )}
          </div>
        ),
        size: 280,
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
        size: 120,
        filterFn: (row, id, value: string[]) => {
          return value.includes(row.getValue(id) as string);
        },
      },
      {
        accessorKey: 'progress',
        header: 'Progress',
        cell: ({ row }) => {
          const progress = row.original.progress || 0;
          return (
            <div className="flex items-center gap-2">
              <div className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.5 }}
                  className={cn(
                    'h-full rounded-full',
                    progress >= 100
                      ? 'bg-green-500'
                      : progress >= 50
                      ? 'bg-blue-500'
                      : 'bg-amber-500'
                  )}
                />
              </div>
              <span className="text-xs text-gray-600 dark:text-gray-400 w-10">
                {formatPercent(progress)}
              </span>
            </div>
          );
        },
        size: 140,
      },
      {
        id: 'timeline',
        header: 'Timeline',
        cell: ({ row }) => {
          const item = row.original;
          if (!item.planned_start || !item.planned_end) return null;
          return (
            <MiniGanttBar
              plannedStart={item.planned_start}
              plannedEnd={item.planned_end}
              currentStart={item.current_start || item.planned_start}
              currentEnd={item.current_end || item.planned_end}
              rangeStart={rangeStart}
              rangeEnd={rangeEnd}
              status={item.status}
            />
          );
        },
        size: 180,
        enableSorting: false,
      },
      {
        accessorKey: 'planned_start',
        header: 'Plan Start',
        cell: ({ row }) => (
          <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
            {formatDate(row.original.planned_start)}
          </span>
        ),
        size: 110,
      },
      {
        accessorKey: 'planned_end',
        header: 'Plan End',
        cell: ({ row }) => (
          <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
            {formatDate(row.original.planned_end)}
          </span>
        ),
        size: 110,
      },
      {
        accessorKey: 'current_start',
        header: 'Actual Start',
        cell: ({ row }) => (
          <span className="text-sm text-gray-900 dark:text-gray-100 whitespace-nowrap">
            {formatDate(row.original.current_start)}
          </span>
        ),
        size: 110,
      },
      {
        accessorKey: 'current_end',
        header: 'Actual End',
        cell: ({ row }) => {
          const item = row.original;
          const delayed = isDelayed(item.planned_end, item.current_end);
          return (
            <span
              className={cn(
                'text-sm whitespace-nowrap',
                delayed ? 'text-red-600 font-medium' : 'text-gray-900 dark:text-gray-100'
              )}
            >
              {formatDate(item.current_end)}
            </span>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'priority',
        header: 'Priority',
        cell: ({ row }) => <PriorityBadge priority={row.original.priority} />,
        size: 90,
        filterFn: (row, id, value: string[]) => {
          return value.includes(row.getValue(id) as string);
        },
      },
      {
        accessorKey: 'complexity',
        header: 'Complexity',
        cell: ({ row }) => <ComplexityBadge complexity={row.original.complexity} />,
        size: 100,
        filterFn: (row, id, value: string[]) => {
          return value.includes(row.getValue(id) as string);
        },
      },
      {
        accessorKey: 'assigned_resources',
        header: 'Resources',
        cell: ({ row }) => {
          const resources = row.original.assigned_resources || [];
          if (resources.length === 0) return <span className="text-gray-400">-</span>;
          return (
            <div className="flex -space-x-2">
              {resources.slice(0, 3).map((r, i) => (
                <div
                  key={i}
                  className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-medium ring-2 ring-white dark:ring-gray-900"
                  title={r}
                >
                  {r.charAt(0).toUpperCase()}
                </div>
              ))}
              {resources.length > 3 && (
                <div className="w-7 h-7 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-xs text-gray-600 dark:text-gray-400 ring-2 ring-white dark:ring-gray-900">
                  +{resources.length - 3}
                </div>
              )}
            </div>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'program',
        header: 'Program',
        cell: ({ row }) => (
          <Badge variant="outline" size="sm">
            {row.original.program || '-'}
          </Badge>
        ),
        size: 120,
      },
      {
        accessorKey: 'project',
        header: 'Project',
        cell: ({ row }) => (
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {row.original.project || '-'}
          </span>
        ),
        size: 150,
      },
      {
        accessorKey: 'phase',
        header: 'Phase',
        cell: ({ row }) => (
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {row.original.phase || '-'}
          </span>
        ),
        size: 100,
      },
    ],
    [rangeStart, rangeEnd]
  );
}

export function WorkItemsTable({
  data,
  isLoading,
  onRowClick,
  onRefresh,
}: WorkItemsTableProps) {
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const { setSelectedIds, clearSelection } = useSelectionStore();
  
  // Table state
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [globalFilter, setGlobalFilter] = useState('');
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Calculate date range for Gantt bars
  const { rangeStart, rangeEnd } = useMemo(() => {
    if (data.length === 0) {
      return {
        rangeStart: new Date(),
        rangeEnd: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000),
      };
    }

    let minDate = new Date();
    let maxDate = new Date();

    data.forEach((item) => {
      if (item.planned_start) {
        const d = new Date(item.planned_start);
        if (d < minDate) minDate = d;
      }
      if (item.current_start) {
        const d = new Date(item.current_start);
        if (d < minDate) minDate = d;
      }
      if (item.planned_end) {
        const d = new Date(item.planned_end);
        if (d > maxDate) maxDate = d;
      }
      if (item.current_end) {
        const d = new Date(item.current_end);
        if (d > maxDate) maxDate = d;
      }
    });

    // Add 10% padding
    const range = maxDate.getTime() - minDate.getTime();
    minDate = new Date(minDate.getTime() - range * 0.05);
    maxDate = new Date(maxDate.getTime() + range * 0.05);

    return { rangeStart: minDate, rangeEnd: maxDate };
  }, [data]);

  const columns = useColumns(rangeStart, rangeEnd);

  // Sync selection with store
  const handleRowSelectionChange = useCallback(
    (updater: RowSelectionState | ((old: RowSelectionState) => RowSelectionState)) => {
      const newSelection = typeof updater === 'function' ? updater(rowSelection) : updater;
      setRowSelection(newSelection);
      
      const selectedTaskCodes = Object.keys(newSelection)
        .filter((key) => newSelection[key])
        .map((idx) => data[parseInt(idx)]?.task_code)
        .filter(Boolean) as string[];
      
      setSelectedIds(selectedTaskCodes);
    },
    [rowSelection, data, setSelectedIds]
  );

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      globalFilter,
    },
    enableRowSelection: true,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: handleRowSelectionChange,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  // Virtualizer for rows
  const { rows } = table.getRowModel();
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 52,
    overscan: 10,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        clearSelection();
        setRowSelection({});
      }
    },
    [clearSelection]
  );

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search work items..."
              value={globalFilter}
              onChange={(e) => setGlobalFilter(e.target.value)}
              className="pl-9 pr-4 py-2 w-64 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {globalFilter && (
              <button
                onClick={() => setGlobalFilter('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Filters toggle */}
          <Button
            variant={showFilters ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter className="w-4 h-4 mr-2" />
            Filters
            {columnFilters.length > 0 && (
              <Badge variant="primary" size="sm" className="ml-2">
                {columnFilters.length}
              </Badge>
            )}
          </Button>

          {/* Column visibility */}
          <div className="relative">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowColumnPicker(!showColumnPicker)}
            >
              <Columns className="w-4 h-4 mr-2" />
              Columns
              <ChevronDown className="w-4 h-4 ml-1" />
            </Button>

            <AnimatePresence>
              {showColumnPicker && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="absolute top-full left-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 z-50"
                >
                  <div className="p-2 max-h-80 overflow-y-auto">
                    {table.getAllLeafColumns().map((column) => {
                      if (column.id === 'select') return null;
                      return (
                        <label
                          key={column.id}
                          className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={column.getIsVisible()}
                            onChange={column.getToggleVisibilityHandler()}
                            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">
                            {typeof column.columnDef.header === 'string'
                              ? column.columnDef.header
                              : column.id}
                          </span>
                          {column.getIsVisible() ? (
                            <Eye className="w-4 h-4 ml-auto text-gray-400" />
                          ) : (
                            <EyeOff className="w-4 h-4 ml-auto text-gray-300" />
                          )}
                        </label>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Row count */}
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {rows.length.toLocaleString()} items
            {Object.keys(rowSelection).length > 0 && (
              <span className="ml-2 text-blue-600">
                ({Object.keys(rowSelection).length} selected)
              </span>
            )}
          </span>

          {/* Export */}
          <Button variant="ghost" size="sm">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>

          {/* Refresh */}
          <Button variant="ghost" size="sm" onClick={onRefresh} disabled={isLoading}>
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* Filter panel */}
      <AnimatePresence>
        {showFilters && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/30 overflow-hidden"
          >
            <FilterPanel
              table={table}
              columnFilters={columnFilters}
              setColumnFilters={setColumnFilters}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Table */}
      <div
        ref={tableContainerRef}
        className="flex-1 overflow-auto"
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        <table className="w-full border-collapse table-fixed" style={{ minWidth: '1400px' }}>
          {/* Define column widths */}
          <colgroup>
            {table.getAllColumns().map((column) => (
              <col key={column.id} style={{ width: column.getSize() }} />
            ))}
          </colgroup>
          <thead className="sticky top-0 bg-gray-50 dark:bg-gray-800/80 backdrop-blur-sm z-10">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    style={{ width: header.getSize() }}
                    className="px-3 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 whitespace-nowrap"
                  >
                    {header.isPlaceholder ? null : (
                      <div
                        className={cn(
                          'flex items-center gap-1',
                          header.column.getCanSort() && 'cursor-pointer select-none hover:text-gray-900 dark:hover:text-gray-200'
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() && (
                          <span className="ml-1">
                            {header.column.getIsSorted() === 'asc' ? (
                              <ArrowUp className="w-3 h-3" />
                            ) : header.column.getIsSorted() === 'desc' ? (
                              <ArrowDown className="w-3 h-3" />
                            ) : (
                              <ArrowUpDown className="w-3 h-3 text-gray-300" />
                            )}
                          </span>
                        )}
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {/* Spacer for virtualization - top */}
            {virtualRows.length > 0 && virtualRows[0].start > 0 && (
              <tr>
                <td style={{ height: virtualRows[0].start }} colSpan={table.getAllColumns().length} />
              </tr>
            )}
            {virtualRows.map((virtualRow) => {
              const row = rows[virtualRow.index];
              return (
                <tr
                  key={row.id}
                  style={{ height: virtualRow.size }}
                  className={cn(
                    'transition-colors',
                    row.getIsSelected()
                      ? 'bg-blue-50 dark:bg-blue-900/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/50',
                    onRowClick && 'cursor-pointer'
                  )}
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      style={{ width: cell.column.getSize() }}
                      className="px-3 py-2 border-b border-gray-100 dark:border-gray-800"
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
            {/* Spacer for virtualization - bottom */}
            {virtualRows.length > 0 && (
              <tr>
                <td 
                  style={{ height: totalSize - virtualRows[virtualRows.length - 1].end }} 
                  colSpan={table.getAllColumns().length} 
                />
              </tr>
            )}
          </tbody>
        </table>

        {/* Empty state */}
        {rows.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center py-16 text-gray-500">
            <Search className="w-12 h-12 mb-4 text-gray-300" />
            <p className="text-lg font-medium">No work items found</p>
            <p className="text-sm">Try adjusting your search or filters</p>
          </div>
        )}

        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 bg-white/50 dark:bg-gray-900/50 flex items-center justify-center">
            <div className="flex items-center gap-3 bg-white dark:bg-gray-800 px-6 py-3 rounded-lg shadow-lg">
              <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Loading work items...
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Filter Panel Component
interface FilterPanelProps {
  table: ReturnType<typeof useReactTable<WorkItem>>;
  columnFilters: ColumnFiltersState;
  setColumnFilters: (filters: ColumnFiltersState) => void;
}

function FilterPanel({ table: _table, columnFilters, setColumnFilters }: FilterPanelProps) {
  const statusOptions = ['Not Started', 'In Progress', 'Completed', 'On Hold', 'Cancelled'];
  const priorityOptions = ['Critical', 'High', 'Medium', 'Low'];
  const complexityOptions = ['Very High', 'High', 'Medium', 'Low'];

  const getFilterValue = (columnId: string): string[] => {
    const filter = columnFilters.find((f) => f.id === columnId);
    return (filter?.value as string[]) || [];
  };

  const setFilterValue = (columnId: string, value: string[]) => {
    if (value.length === 0) {
      setColumnFilters(columnFilters.filter((f) => f.id !== columnId));
    } else {
      const newFilters = columnFilters.filter((f) => f.id !== columnId);
      newFilters.push({ id: columnId, value });
      setColumnFilters(newFilters);
    }
  };

  const toggleFilter = (columnId: string, option: string) => {
    const current = getFilterValue(columnId);
    if (current.includes(option)) {
      setFilterValue(columnId, current.filter((v) => v !== option));
    } else {
      setFilterValue(columnId, [...current, option]);
    }
  };

  return (
    <div className="px-4 py-3 flex flex-wrap items-center gap-4">
      {/* Status filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Status:</span>
        <div className="flex gap-1">
          {statusOptions.map((status) => (
            <button
              key={status}
              onClick={() => toggleFilter('status', status)}
              className={cn(
                'px-2 py-1 text-xs rounded-full transition-colors',
                getFilterValue('status').includes(status)
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
              )}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      {/* Priority filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Priority:</span>
        <div className="flex gap-1">
          {priorityOptions.map((priority) => (
            <button
              key={priority}
              onClick={() => toggleFilter('priority', priority)}
              className={cn(
                'px-2 py-1 text-xs rounded-full transition-colors',
                getFilterValue('priority').includes(priority)
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
              )}
            >
              {priority}
            </button>
          ))}
        </div>
      </div>

      {/* Complexity filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Complexity:</span>
        <div className="flex gap-1">
          {complexityOptions.map((complexity) => (
            <button
              key={complexity}
              onClick={() => toggleFilter('complexity', complexity)}
              className={cn(
                'px-2 py-1 text-xs rounded-full transition-colors',
                getFilterValue('complexity').includes(complexity)
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
              )}
            >
              {complexity}
            </button>
          ))}
        </div>
      </div>

      {/* Clear filters */}
      {columnFilters.length > 0 && (
        <button
          onClick={() => setColumnFilters([])}
          className="ml-auto text-xs text-red-600 hover:text-red-700 flex items-center gap-1"
        >
          <X className="w-3 h-3" />
          Clear all filters
        </button>
      )}
    </div>
  );
}
