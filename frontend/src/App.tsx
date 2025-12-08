/**
 * Tracky PM - Main App Component
 * Sets up routing and layout
 */
import { Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy, useEffect } from 'react';
import { MainLayout } from './components/layout/MainLayout';
import { Spinner } from './components/ui/Progress';
import { useThemeStore } from './stores';

// Lazy load pages for code splitting
const DashboardPage = lazy(() => import('./pages/DashboardPage').then(m => ({ default: m.DashboardPage })));
const WorkItemsPage = lazy(() => import('./pages/WorkItemsPage').then(m => ({ default: m.WorkItemsPage })));
const ResourcesPage = lazy(() => import('./pages/ResourcesPage').then(m => ({ default: m.ResourcesPage })));
const AuditLogsPage = lazy(() => import('./pages/AuditLogsPage').then(m => ({ default: m.AuditLogsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage })));
const ProgramsPage = lazy(() => import('./pages/ProgramsPage').then(m => ({ default: m.ProgramsPage })));
const ImportPage = lazy(() => import('./pages/ImportPage').then(m => ({ default: m.ImportPage })));
const FlaggedItemsPage = lazy(() => import('./pages/FlaggedItemsPage').then(m => ({ default: m.FlaggedItemsPage })));
const ImportHistoryPage = lazy(() => import('./pages/ImportHistoryPage').then(m => ({ default: m.ImportHistoryPage })));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage').then(m => ({ default: m.AnalyticsPage })));
const BaselinesPage = lazy(() => import('./pages/BaselinesPage').then(m => ({ default: m.BaselinesPage })));
const AlertsPage = lazy(() => import('./pages/AlertsPage').then(m => ({ default: m.AlertsPage })));
const AlertResponsePage = lazy(() => import('./pages/AlertResponsePage').then(m => ({ default: m.AlertResponsePage })));
const HolidaysPage = lazy(() => import('./pages/HolidaysPage').then(m => ({ default: m.HolidaysPage })));

// Loading fallback
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-4">
        <Spinner size="lg" />
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading...</p>
      </div>
    </div>
  );
}

function App() {
  const { theme } = useThemeStore();

  // Apply theme class to document
  useEffect(() => {
    const root = document.documentElement;
    
    if (theme === 'dark') {
      root.classList.add('dark');
    } else if (theme === 'light') {
      root.classList.remove('dark');
    } else {
      // System preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      if (prefersDark) {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }
    }

    // Save theme preference
    localStorage.setItem('tracky-theme', theme);
  }, [theme]);

  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        {/* Default redirect to dashboard */}
        <Route index element={<Navigate to="/dashboard" replace />} />
        
        {/* Main pages */}
        <Route
          path="dashboard"
          element={
            <Suspense fallback={<PageLoader />}>
              <DashboardPage />
            </Suspense>
          }
        />
        <Route
          path="work-items"
          element={
            <Suspense fallback={<PageLoader />}>
              <WorkItemsPage />
            </Suspense>
          }
        />
        <Route
          path="resources"
          element={
            <Suspense fallback={<PageLoader />}>
              <ResourcesPage />
            </Suspense>
          }
        />
        <Route
          path="audit"
          element={
            <Suspense fallback={<PageLoader />}>
              <AuditLogsPage />
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<PageLoader />}>
              <SettingsPage />
            </Suspense>
          }
        />
        <Route
          path="programs"
          element={
            <Suspense fallback={<PageLoader />}>
              <ProgramsPage />
            </Suspense>
          }
        />
        <Route
          path="import"
          element={
            <Suspense fallback={<PageLoader />}>
              <ImportPage />
            </Suspense>
          }
        />
        <Route
          path="flagged"
          element={
            <Suspense fallback={<PageLoader />}>
              <FlaggedItemsPage />
            </Suspense>
          }
        />
        <Route
          path="history"
          element={
            <Suspense fallback={<PageLoader />}>
              <ImportHistoryPage />
            </Suspense>
          }
        />
        <Route
          path="analytics"
          element={
            <Suspense fallback={<PageLoader />}>
              <AnalyticsPage />
            </Suspense>
          }
        />
        <Route
          path="baselines"
          element={
            <Suspense fallback={<PageLoader />}>
              <BaselinesPage />
            </Suspense>
          }
        />
        <Route
          path="alerts"
          element={
            <Suspense fallback={<PageLoader />}>
              <AlertsPage />
            </Suspense>
          }
        />
        <Route
          path="holidays"
          element={
            <Suspense fallback={<PageLoader />}>
              <HolidaysPage />
            </Suspense>
          }
        />
        
        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
      
      {/* Magic Link Response - Outside main layout (no auth required) */}
      <Route
        path="/respond/:token"
        element={
          <Suspense fallback={<PageLoader />}>
            <AlertResponsePage />
          </Suspense>
        }
      />
    </Routes>
  );
}

export default App;
