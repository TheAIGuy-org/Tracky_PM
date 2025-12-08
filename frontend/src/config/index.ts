/**
 * Environment configuration
 */
export const config = {
  // API Configuration
  apiUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  
  // Supabase Configuration (for realtime)
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL || '',
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || '',
  
  // Feature Flags
  enableRealtime: import.meta.env.VITE_ENABLE_REALTIME !== 'false',
  
  // UI Configuration
  defaultPageSize: 50,
  maxPageSize: 100,
  virtualizedRowThreshold: 100,
  
  // Polling intervals (ms) - fallback when realtime is disabled
  pollingInterval: 30000,
  healthCheckInterval: 60000,
} as const;

export type Config = typeof config;
