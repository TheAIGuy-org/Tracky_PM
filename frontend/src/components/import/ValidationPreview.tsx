/**
 * Validation Preview component - Shows parsed data and validation results
 */
import { motion } from 'framer-motion';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileSpreadsheet,
  Users,
  GitBranch,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { useState } from 'react';
import { cn, formatNumber } from '../../lib/utils';
import { Card, Badge } from '../ui';
import type { ValidateResponse, ImportWarning, ImportError } from '../../types';

interface ValidationPreviewProps {
  result: ValidateResponse;
  fileName: string;
}

export function ValidationPreview({ result, fileName }: ValidationPreviewProps) {
  const { summary, validation } = result;
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['summary'])
  );

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  return (
    <div className="space-y-4">
      {/* Status Banner */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className={cn(
          'rounded-xl p-4 border-2',
          validation.is_valid
            ? 'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800'
            : 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800'
        )}
      >
        <div className="flex items-center gap-3">
          {validation.is_valid ? (
            <CheckCircle2 className="h-6 w-6 text-green-500" />
          ) : (
            <XCircle className="h-6 w-6 text-red-500" />
          )}
          <div>
            <p
              className={cn(
                'font-semibold',
                validation.is_valid
                  ? 'text-green-800 dark:text-green-200'
                  : 'text-red-800 dark:text-red-200'
              )}
            >
              {validation.is_valid
                ? 'Validation Passed'
                : 'Validation Failed'}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {fileName}
            </p>
          </div>
        </div>
      </motion.div>

      {/* Summary Section */}
      <SectionCard
        title="Parsed Data Summary"
        isExpanded={expandedSections.has('summary')}
        onToggle={() => toggleSection('summary')}
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryItem
            icon={<FileSpreadsheet className="h-5 w-5" />}
            label="Work Items"
            value={summary.work_items}
            color="blue"
          />
          <SummaryItem
            icon={<Users className="h-5 w-5" />}
            label="Resources"
            value={summary.resources}
            color="green"
          />
          <SummaryItem
            icon={<GitBranch className="h-5 w-5" />}
            label="Dependencies"
            value={summary.dependencies}
            color="purple"
          />
          <SummaryItem
            icon={<FileSpreadsheet className="h-5 w-5" />}
            label="Programs"
            value={summary.programs}
            color="amber"
          />
        </div>
      </SectionCard>

      {/* Warnings Section */}
      {validation.warnings.length > 0 && (
        <SectionCard
          title={`Warnings (${validation.warnings.length})`}
          isExpanded={expandedSections.has('warnings')}
          onToggle={() => toggleSection('warnings')}
          variant="warning"
        >
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {validation.warnings.map((warning, index) => (
              <WarningItem key={index} warning={warning} />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Errors Section */}
      {validation.errors.length > 0 && (
        <SectionCard
          title={`Errors (${validation.errors.length})`}
          isExpanded={expandedSections.has('errors')}
          onToggle={() => toggleSection('errors')}
          variant="error"
        >
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {validation.errors.map((error, index) => (
              <ErrorItem key={index} error={error} />
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

// Section Card Component
interface SectionCardProps {
  title: string;
  isExpanded: boolean;
  onToggle: () => void;
  variant?: 'default' | 'warning' | 'error';
  children: React.ReactNode;
}

function SectionCard({
  title,
  isExpanded,
  onToggle,
  variant = 'default',
  children,
}: SectionCardProps) {
  const variants = {
    default: 'border-gray-200 dark:border-gray-800',
    warning: 'border-amber-200 dark:border-amber-800/50',
    error: 'border-red-200 dark:border-red-800/50',
  };

  const iconColors = {
    default: 'text-gray-500',
    warning: 'text-amber-500',
    error: 'text-red-500',
  };

  return (
    <Card className={cn('overflow-hidden', variants[variant])}>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {variant === 'warning' && (
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          )}
          {variant === 'error' && (
            <XCircle className="h-4 w-4 text-red-500" />
          )}
          <span className="font-medium text-gray-900 dark:text-white">
            {title}
          </span>
        </div>
        {isExpanded ? (
          <ChevronDown className={cn('h-4 w-4', iconColors[variant])} />
        ) : (
          <ChevronRight className={cn('h-4 w-4', iconColors[variant])} />
        )}
      </button>
      {isExpanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="px-4 pb-4"
        >
          {children}
        </motion.div>
      )}
    </Card>
  );
}

// Summary Item Component
interface SummaryItemProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: 'blue' | 'green' | 'purple' | 'amber';
}

function SummaryItem({ icon, label, value, color }: SummaryItemProps) {
  const colors = {
    blue: 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400',
    green: 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400',
    purple: 'bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400',
    amber: 'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400',
  };

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
      <div className={cn('p-2 rounded-lg', colors[color])}>{icon}</div>
      <div>
        <p className="text-2xl font-bold text-gray-900 dark:text-white">
          {formatNumber(value)}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      </div>
    </div>
  );
}

// Warning Item Component
function WarningItem({ warning }: { warning: ImportWarning }) {
  return (
    <div className="flex items-start gap-2 p-2 rounded-lg bg-amber-50 dark:bg-amber-900/10">
      <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-amber-800 dark:text-amber-200">
          {warning.message}
        </p>
        <div className="mt-1 flex gap-2 flex-wrap">
          {warning.row && (
            <Badge variant="warning" size="sm">
              Row {warning.row}
            </Badge>
          )}
          {warning.field && (
            <Badge variant="outline" size="sm">
              {warning.field}
            </Badge>
          )}
          {warning.type && (
            <Badge variant="default" size="sm">
              {warning.type}
            </Badge>
          )}
        </div>
      </div>
    </div>
  );
}

// Error Item Component
function ErrorItem({ error }: { error: ImportError }) {
  return (
    <div className="flex items-start gap-2 p-2 rounded-lg bg-red-50 dark:bg-red-900/10">
      <XCircle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-red-800 dark:text-red-200">
          {error.message}
        </p>
        <div className="mt-1 flex gap-2 flex-wrap">
          {error.row && (
            <Badge variant="danger" size="sm">
              Row {error.row}
            </Badge>
          )}
          {error.field && (
            <Badge variant="outline" size="sm">
              {error.field}
            </Badge>
          )}
          {error.value && (
            <Badge variant="default" size="sm" className="truncate max-w-[200px]">
              Value: {error.value}
            </Badge>
          )}
        </div>
      </div>
    </div>
  );
}
