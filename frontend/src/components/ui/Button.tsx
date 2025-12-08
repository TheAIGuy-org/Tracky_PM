/**
 * Button component with variants using CVA (Class Variance Authority)
 * Industry-standard accessible button with loading states
 */
import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

const buttonVariants = cva(
  // Base styles
  `inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg 
   text-sm font-medium transition-all duration-200
   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2
   disabled:pointer-events-none disabled:opacity-50
   active:scale-[0.98]`,
  {
    variants: {
      variant: {
        primary: `
          bg-brand-600 text-white shadow-sm
          hover:bg-brand-700 hover:shadow-md
          dark:bg-brand-500 dark:hover:bg-brand-600
        `,
        secondary: `
          bg-gray-100 text-gray-900 shadow-sm
          hover:bg-gray-200 hover:shadow-md
          dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700
        `,
        outline: `
          border-2 border-gray-200 bg-transparent text-gray-700
          hover:bg-gray-50 hover:border-gray-300
          dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800/50
        `,
        ghost: `
          bg-transparent text-gray-600
          hover:bg-gray-100 hover:text-gray-900
          dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100
        `,
        danger: `
          bg-red-600 text-white shadow-sm
          hover:bg-red-700 hover:shadow-md
          dark:bg-red-500 dark:hover:bg-red-600
        `,
        success: `
          bg-green-600 text-white shadow-sm
          hover:bg-green-700 hover:shadow-md
          dark:bg-green-500 dark:hover:bg-green-600
        `,
        link: `
          text-brand-600 underline-offset-4
          hover:underline
          dark:text-brand-400
        `,
      },
      size: {
        xs: 'h-7 px-2.5 text-xs rounded-md',
        sm: 'h-8 px-3 text-sm rounded-md',
        md: 'h-10 px-4 text-sm',
        lg: 'h-11 px-6 text-base',
        xl: 'h-12 px-8 text-base',
        icon: 'h-10 w-10',
        'icon-sm': 'h-8 w-8',
        'icon-xs': 'h-6 w-6 rounded-md',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      isLoading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : leftIcon ? (
          leftIcon
        ) : null}
        {children}
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = 'Button';

export { Button, buttonVariants };
