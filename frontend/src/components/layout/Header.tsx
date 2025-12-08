/**
 * Header component with search, notifications, and user menu
 */
import { useState } from 'react';
import {
  Bell,
  Sun,
  Moon,
  Upload,
  Activity,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useThemeStore, useImportWizardStore } from '../../stores';
import { useHealthCheck } from '../../lib/queries';
import { Button, SearchInput } from '../ui';

interface HeaderProps {
  title?: string;
}

export function Header({ title }: HeaderProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const { setTheme, resolvedTheme } = useThemeStore();
  const { openWizard } = useImportWizardStore();
  
  // Health check query
  const { data: health, isLoading: healthLoading } = useHealthCheck();

  const toggleTheme = () => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <header className="h-16 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 flex items-center justify-between">
      {/* Left - Title & Search */}
      <div className="flex items-center gap-6">
        {title && (
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
            {title}
          </h1>
        )}
        <div className="hidden md:block w-64">
          <SearchInput
            placeholder="Search tasks, resources..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onClear={() => setSearchQuery('')}
          />
        </div>
      </div>

      {/* Right - Actions */}
      <div className="flex items-center gap-2">
        {/* Server Status */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800">
          <Activity
            className={cn(
              'h-4 w-4',
              healthLoading
                ? 'text-gray-400 animate-pulse'
                : health?.status === 'healthy' || health?.status === 'degraded'
                ? 'text-green-500'
                : 'text-red-500'
            )}
          />
          <span className="text-xs text-gray-600 dark:text-gray-400">
            {healthLoading 
              ? 'Checking...' 
              : health?.status === 'healthy' || health?.status === 'degraded'
              ? 'API Online' 
              : 'API Offline'}
          </span>
        </div>

        {/* Import Button */}
        <Button onClick={openWizard} size="sm">
          <Upload className="h-4 w-4" aria-hidden="true" />
          Import
        </Button>

        {/* Notifications */}
        <Button variant="ghost" size="icon-sm" className="relative" aria-label="Notifications">
          <Bell className="h-4 w-4" aria-hidden="true" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" aria-hidden="true" />
          <span className="sr-only">You have unread notifications</span>
        </Button>

        {/* Theme Toggle */}
        <Button 
          variant="ghost" 
          size="icon-sm" 
          onClick={toggleTheme}
          aria-label={resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {resolvedTheme === 'dark' ? (
            <Sun className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Moon className="h-4 w-4" aria-hidden="true" />
          )}
        </Button>

        {/* User Avatar */}
        <button 
          className="ml-2 w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center text-white text-sm font-medium focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          aria-label="User menu"
        >
          PM
        </button>
      </div>
    </header>
  );
}
