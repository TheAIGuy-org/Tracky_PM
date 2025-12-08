/**
 * Zustand stores for UI state management
 * Following the rule: "Server state in TanStack Query, UI state in Zustand"
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { WorkStatus, ImportResponse, ValidateResponse } from '../types';

// ==========================================
// SIDEBAR & NAVIGATION STORE
// ==========================================

interface SidebarState {
  isCollapsed: boolean;
  activeSection: string;
  toggleCollapsed: () => void;
  setActiveSection: (section: string) => void;
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      isCollapsed: false,
      activeSection: 'dashboard',
      toggleCollapsed: () => set((state) => ({ isCollapsed: !state.isCollapsed })),
      setActiveSection: (section) => set({ activeSection: section }),
    }),
    {
      name: 'tracky-sidebar',
      storage: createJSONStorage(() => localStorage),
    }
  )
);

// ==========================================
// IMPORT WIZARD STORE
// ==========================================

export type ImportWizardStep = 'upload' | 'validate' | 'execute' | 'complete';

interface ImportWizardState {
  isOpen: boolean;
  currentStep: ImportWizardStep;
  selectedFile: File | null;
  validationResult: ValidateResponse | null;
  importResult: ImportResponse | null;
  importOptions: {
    performGhostCheck: boolean;
    triggerRecalculation: boolean;
    saveBaselineVersion: boolean;
    dryRun: boolean;
  };
  
  // Actions
  openWizard: () => void;
  closeWizard: () => void;
  setStep: (step: ImportWizardStep) => void;
  setFile: (file: File | null) => void;
  setValidationResult: (result: ValidateResponse | null) => void;
  setImportResult: (result: ImportResponse | null) => void;
  setImportOption: <K extends keyof ImportWizardState['importOptions']>(
    key: K,
    value: ImportWizardState['importOptions'][K]
  ) => void;
  reset: () => void;
}

const initialImportOptions = {
  performGhostCheck: true,
  triggerRecalculation: true,
  saveBaselineVersion: true,
  dryRun: false,
};

export const useImportWizardStore = create<ImportWizardState>()((set) => ({
  isOpen: false,
  currentStep: 'upload',
  selectedFile: null,
  validationResult: null,
  importResult: null,
  importOptions: initialImportOptions,
  
  openWizard: () => set({ isOpen: true, currentStep: 'upload' }),
  closeWizard: () => set({ isOpen: false }),
  setStep: (step) => set({ currentStep: step }),
  setFile: (file) => set({ selectedFile: file }),
  setValidationResult: (result) => set({ validationResult: result }),
  setImportResult: (result) => set({ importResult: result }),
  setImportOption: (key, value) =>
    set((state) => ({
      importOptions: { ...state.importOptions, [key]: value },
    })),
  reset: () =>
    set({
      currentStep: 'upload',
      selectedFile: null,
      validationResult: null,
      importResult: null,
      importOptions: initialImportOptions,
    }),
}));

// ==========================================
// TABLE FILTERS STORE
// ==========================================

interface TableFiltersState {
  searchQuery: string;
  statusFilter: WorkStatus | 'all';
  programFilter: string | null;
  resourceFilter: string | null;
  showDelayed: boolean;
  showCriticalPath: boolean;
  showFlagged: boolean;
  
  // Date range
  dateRangeStart: string | null;
  dateRangeEnd: string | null;
  
  // Sorting
  sortField: string | null;
  sortDirection: 'asc' | 'desc';
  
  // Actions
  setSearchQuery: (query: string) => void;
  setStatusFilter: (status: WorkStatus | 'all') => void;
  setProgramFilter: (programId: string | null) => void;
  setResourceFilter: (resourceId: string | null) => void;
  setShowDelayed: (show: boolean) => void;
  setShowCriticalPath: (show: boolean) => void;
  setShowFlagged: (show: boolean) => void;
  setDateRange: (start: string | null, end: string | null) => void;
  setSort: (field: string | null, direction: 'asc' | 'desc') => void;
  resetFilters: () => void;
}

const initialFilters = {
  searchQuery: '',
  statusFilter: 'all' as const,
  programFilter: null,
  resourceFilter: null,
  showDelayed: false,
  showCriticalPath: false,
  showFlagged: false,
  dateRangeStart: null,
  dateRangeEnd: null,
  sortField: null,
  sortDirection: 'asc' as const,
};

export const useTableFiltersStore = create<TableFiltersState>()((set) => ({
  ...initialFilters,
  
  setSearchQuery: (query) => set({ searchQuery: query }),
  setStatusFilter: (status) => set({ statusFilter: status }),
  setProgramFilter: (programId) => set({ programFilter: programId }),
  setResourceFilter: (resourceId) => set({ resourceFilter: resourceId }),
  setShowDelayed: (show) => set({ showDelayed: show }),
  setShowCriticalPath: (show) => set({ showCriticalPath: show }),
  setShowFlagged: (show) => set({ showFlagged: show }),
  setDateRange: (start, end) => set({ dateRangeStart: start, dateRangeEnd: end }),
  setSort: (field, direction) => set({ sortField: field, sortDirection: direction }),
  resetFilters: () => set(initialFilters),
}));

// ==========================================
// TOAST NOTIFICATIONS STORE
// ==========================================

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastState {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => string;
  removeToast: (id: string) => void;
  clearToasts: () => void;
}

export const useToastStore = create<ToastState>()((set) => ({
  toasts: [],
  
  addToast: (toast) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    set((state) => ({
      toasts: [...state.toasts, { ...toast, id }],
    }));
    
    // Auto-remove after duration
    const duration = toast.duration ?? 5000;
    if (duration > 0) {
      setTimeout(() => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }));
      }, duration);
    }
    
    return id;
  },
  
  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
  
  clearToasts: () => set({ toasts: [] }),
}));

// ==========================================
// MODAL STORE
// ==========================================

type ModalType = 
  | 'confirmDelete'
  | 'resolveFlagged'
  | 'viewAuditLog'
  | 'baselineComparison'
  | 'resourceDetail'
  | 'workItemDetail';

interface ModalState {
  activeModal: ModalType | null;
  modalData: Record<string, unknown>;
  openModal: (type: ModalType, data?: Record<string, unknown>) => void;
  closeModal: () => void;
}

export const useModalStore = create<ModalState>()((set) => ({
  activeModal: null,
  modalData: {},
  
  openModal: (type, data = {}) => set({ activeModal: type, modalData: data }),
  closeModal: () => set({ activeModal: null, modalData: {} }),
}));

// ==========================================
// THEME STORE
// ==========================================

type Theme = 'light' | 'dark' | 'system';

interface ThemeState {
  theme: Theme;
  resolvedTheme: 'light' | 'dark';
  setTheme: (theme: Theme) => void;
}

const getSystemTheme = (): 'light' | 'dark' => {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, _get) => ({
      theme: 'system',
      resolvedTheme: getSystemTheme(),
      
      setTheme: (theme) => {
        const resolved = theme === 'system' ? getSystemTheme() : theme;
        set({ theme, resolvedTheme: resolved });
        
        // Apply to document
        if (resolved === 'dark') {
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
        }
      },
    }),
    {
      name: 'tracky-theme',
      storage: createJSONStorage(() => localStorage),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolved = state.theme === 'system' ? getSystemTheme() : state.theme;
          if (resolved === 'dark') {
            document.documentElement.classList.add('dark');
          }
        }
      },
    }
  )
);

// ==========================================
// SELECTED ITEMS STORE (for bulk operations)
// ==========================================

interface SelectionState {
  selectedIds: Set<string>;
  selectItem: (id: string) => void;
  deselectItem: (id: string) => void;
  toggleItem: (id: string) => void;
  selectAll: (ids: string[]) => void;
  setSelectedIds: (ids: string[]) => void;
  clearSelection: () => void;
  isSelected: (id: string) => boolean;
}

export const useSelectionStore = create<SelectionState>()((set, get) => ({
  selectedIds: new Set(),
  
  selectItem: (id) =>
    set((state) => ({
      selectedIds: new Set(state.selectedIds).add(id),
    })),
  
  deselectItem: (id) =>
    set((state) => {
      const newSet = new Set(state.selectedIds);
      newSet.delete(id);
      return { selectedIds: newSet };
    }),
  
  toggleItem: (id) =>
    set((state) => {
      const newSet = new Set(state.selectedIds);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return { selectedIds: newSet };
    }),
  
  selectAll: (ids) => set({ selectedIds: new Set(ids) }),
  
  setSelectedIds: (ids) => set({ selectedIds: new Set(ids) }),
  
  clearSelection: () => set({ selectedIds: new Set() }),
  
  isSelected: (id: string): boolean => get().selectedIds.has(id),
}));
