/**
 * Main layout wrapper component
 */
import { Outlet } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useSidebarStore } from '../../stores';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { ToastContainer } from '../ui';
import { ImportWizard } from '../import';

interface MainLayoutProps {
  title?: string;
}

export function MainLayout({ title }: MainLayoutProps) {
  const { isCollapsed } = useSidebarStore();

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content */}
      <motion.div
        initial={false}
        animate={{ marginLeft: isCollapsed ? 72 : 256 }}
        transition={{ duration: 0.2, ease: 'easeInOut' }}
        className="min-h-screen flex flex-col"
      >
        {/* Header */}
        <Header title={title} />

        {/* Page Content */}
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </motion.div>

      {/* Global Components */}
      <ToastContainer />
      <ImportWizard />
    </div>
  );
}
