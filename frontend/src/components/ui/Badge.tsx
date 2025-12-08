/**
 * Badge component for status indicators and labels
 */
import { type HTMLAttributes } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const badgeVariants = cva(
  `inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium
   transition-colors`,
  {
    variants: {
      variant: {
        default: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
        primary: 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400',
        secondary: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
        success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
        warning: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
        danger: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
        info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
        purple: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
        outline: 'border border-gray-200 text-gray-700 dark:border-gray-700 dark:text-gray-300',
      },
      size: {
        sm: 'text-2xs px-2 py-0.5',
        md: 'text-xs px-2.5 py-0.5',
        lg: 'text-sm px-3 py-1',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean;
  dotColor?: string;
}

function Badge({
  className,
  variant,
  size,
  dot,
  dotColor,
  children,
  ...props
}: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, size, className }))} {...props}>
      {dot && (
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            dotColor || 'bg-current'
          )}
        />
      )}
      {children}
    </span>
  );
}

// Status-specific badge variants
export function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, VariantProps<typeof badgeVariants>['variant']> = {
    'Not Started': 'default',
    'In Progress': 'info',
    Completed: 'success',
    'On Hold': 'warning',
    Cancelled: 'danger',
    // Program statuses
    Planned: 'default',
    Active: 'info',
    // Resource statuses
    Available: 'success',
    'At-Risk': 'warning',
    'Over-Allocated': 'danger',
  };

  return (
    <Badge variant={variants[status] || 'default'} dot>
      {status}
    </Badge>
  );
}

// Priority badge
export function PriorityBadge({ priority }: { priority?: number | string }) {
  if (priority === undefined || priority === null) {
    return <Badge variant="default">-</Badge>;
  }
  
  // Handle numeric priority
  const numericPriority = typeof priority === 'string' ? parseInt(priority, 10) : priority;
  
  const config: Record<number, { label: string; variant: VariantProps<typeof badgeVariants>['variant'] }> = {
    1: { label: 'Critical', variant: 'danger' },
    2: { label: 'High', variant: 'warning' },
    3: { label: 'Medium', variant: 'info' },
    4: { label: 'Low', variant: 'default' },
    5: { label: 'Lowest', variant: 'default' },
  };

  const { label, variant } = config[numericPriority] || { label: `P${priority}`, variant: 'default' };

  return <Badge variant={variant}>{label}</Badge>;
}

// Complexity badge
export function ComplexityBadge({ complexity }: { complexity?: string }) {
  if (!complexity) {
    return <Badge variant="default">-</Badge>;
  }
  
  const variants: Record<string, VariantProps<typeof badgeVariants>['variant']> = {
    Low: 'success',
    Medium: 'warning',
    High: 'danger',
  };

  return <Badge variant={variants[complexity] || 'default'}>{complexity}</Badge>;
}

export { Badge, badgeVariants };
