/**
 * Sidebar navigation component
 */
import { NavLink, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  Upload,
  Table2,
  Users,
  FolderKanban,
  History,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  BarChart3,
  Layers,
  Bell,
  Calendar,
  FileSpreadsheet,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useSidebarStore } from '../../stores';
import { Button } from '../ui';

const navItems = [
  {
    section: 'Main',
    items: [
      { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
      { to: '/work-items', icon: Table2, label: 'Work Items' },
      { to: '/resources', icon: Users, label: 'Resources' },
      { to: '/programs', icon: FolderKanban, label: 'Programs' },
    ],
  },
  {
    section: 'Proactive',
    items: [
      { to: '/alerts', icon: Bell, label: 'Alerts' },
      { to: '/holidays', icon: Calendar, label: 'Holidays' },
    ],
  },
  {
    section: 'Import',
    items: [
      { to: '/import', icon: Upload, label: 'Import Data' },
      { to: '/flagged', icon: AlertTriangle, label: 'Flagged Items' },
      { to: '/history', icon: History, label: 'Import History' },
    ],
  },
  {
    section: 'Analytics',
    items: [
      { to: '/analytics', icon: BarChart3, label: 'Analytics' },
      { to: '/baselines', icon: Layers, label: 'Baselines' },
    ],
  },
];

export function Sidebar() {
  const { isCollapsed, toggleCollapsed } = useSidebarStore();
  const location = useLocation();

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 72 : 256 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className={cn(
        'fixed left-0 top-0 h-screen z-40',
        'bg-white dark:bg-gray-900',
        'border-r border-gray-200 dark:border-gray-800',
        'flex flex-col'
      )}
    >
      {/* Logo */}
      <div className="h-16 flex items-center px-4 border-b border-gray-100 dark:border-gray-800">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center shadow-lg shadow-brand-500/20">
            <FileSpreadsheet className="h-5 w-5 text-white" />
          </div>
          {!isCollapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <h1 className="text-lg font-bold text-gray-900 dark:text-white">
                Tracky
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Project Manager
              </p>
            </motion.div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-6">
        {navItems.map((section) => (
          <div key={section.section}>
            {!isCollapsed && (
              <p className="px-3 mb-2 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                {section.section}
              </p>
            )}
            <div className="space-y-1">
              {section.items.map((item) => {
                const isActive = location.pathname === item.to;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200',
                      'hover:bg-gray-100 dark:hover:bg-gray-800',
                      isActive
                        ? 'bg-brand-50 text-brand-600 dark:bg-brand-900/20 dark:text-brand-400'
                        : 'text-gray-600 dark:text-gray-400'
                    )}
                  >
                    <item.icon className="h-5 w-5 flex-shrink-0" />
                    {!isCollapsed && (
                      <span className="font-medium">{item.label}</span>
                    )}
                    {isActive && !isCollapsed && (
                      <motion.div
                        layoutId="activeIndicator"
                        className="ml-auto w-1.5 h-1.5 rounded-full bg-brand-500"
                      />
                    )}
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse Button */}
      <div className="p-3 border-t border-gray-100 dark:border-gray-800">
        <Button
          variant="ghost"
          size={isCollapsed ? 'icon' : 'md'}
          onClick={toggleCollapsed}
          className="w-full justify-center"
        >
          {isCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <>
              <ChevronLeft className="h-4 w-4" />
              <span>Collapse</span>
            </>
          )}
        </Button>
      </div>
    </motion.aside>
  );
}
