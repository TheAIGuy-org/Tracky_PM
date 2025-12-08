/**
 * Card component with glass-morphism and elevation variants
 */
import { type HTMLAttributes, forwardRef } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const cardVariants = cva(
  'rounded-xl transition-all duration-200',
  {
    variants: {
      variant: {
        default: `
          bg-white border border-gray-200
          dark:bg-gray-900 dark:border-gray-800
        `,
        elevated: `
          bg-white shadow-card hover:shadow-card-hover
          dark:bg-gray-900 dark:shadow-none dark:border dark:border-gray-800
        `,
        glass: `
          bg-white/80 backdrop-blur-md border border-white/20
          dark:bg-gray-900/80 dark:border-gray-700/50
        `,
        outline: `
          bg-transparent border-2 border-gray-200
          dark:border-gray-700
        `,
        gradient: `
          bg-gradient-to-br from-brand-500/10 to-purple-500/10
          border border-brand-200/50
          dark:from-brand-500/5 dark:to-purple-500/5 dark:border-brand-700/30
        `,
        interactive: `
          bg-white border border-gray-200 cursor-pointer
          hover:border-brand-300 hover:shadow-glow-sm
          dark:bg-gray-900 dark:border-gray-800 dark:hover:border-brand-600
        `,
      },
      padding: {
        none: '',
        sm: 'p-3',
        md: 'p-4',
        lg: 'p-6',
        xl: 'p-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      padding: 'md',
    },
  }
);

export interface CardProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {
  hover?: boolean;
}

const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, padding, hover, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        cardVariants({ variant, padding, className }),
        hover && 'hover:shadow-md hover:border-brand-300 dark:hover:border-brand-600 cursor-pointer'
      )}
      {...props}
    />
  )
);

Card.displayName = 'Card';

// Card sub-components
const CardHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('flex flex-col space-y-1.5 pb-4', className)}
      {...props}
    />
  )
);
CardHeader.displayName = 'CardHeader';

const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn(
        'text-lg font-semibold leading-none tracking-tight text-gray-900 dark:text-white',
        className
      )}
      {...props}
    />
  )
);
CardTitle.displayName = 'CardTitle';

const CardDescription = forwardRef<HTMLParagraphElement, HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn('text-sm text-gray-500 dark:text-gray-400', className)}
      {...props}
    />
  )
);
CardDescription.displayName = 'CardDescription';

const CardContent = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('', className)} {...props} />
  )
);
CardContent.displayName = 'CardContent';

const CardFooter = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('flex items-center pt-4 border-t border-gray-100 dark:border-gray-800', className)}
      {...props}
    />
  )
);
CardFooter.displayName = 'CardFooter';

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter, cardVariants };
