/**
 * Settings Page
 * Application settings and configuration
 */
import { useState } from 'react';
import {
  Settings,
  Moon,
  Sun,
  Monitor,
  Bell,
  Shield,
  Database,
  Palette,
  Check,
  Info,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { useThemeStore } from '../stores';
import { cn } from '../lib/utils';

type SettingsTab = 'appearance' | 'notifications' | 'data' | 'security' | 'about';

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('appearance');

  const tabs: { key: SettingsTab; label: string; icon: React.ElementType }[] = [
    { key: 'appearance', label: 'Appearance', icon: Palette },
    { key: 'notifications', label: 'Notifications', icon: Bell },
    { key: 'data', label: 'Data & Import', icon: Database },
    { key: 'security', label: 'Security', icon: Shield },
    { key: 'about', label: 'About', icon: Info },
  ];

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-64 border-r border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 p-4">
        <div className="flex items-center gap-2 mb-6 px-2">
          <Settings className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Settings
          </h1>
        </div>

        <nav className="space-y-1">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                activeTab === key
                  ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto p-6">
          {activeTab === 'appearance' && <AppearanceSettings />}
          {activeTab === 'notifications' && <NotificationSettings />}
          {activeTab === 'data' && <DataSettings />}
          {activeTab === 'security' && <SecuritySettings />}
          {activeTab === 'about' && <AboutSection />}
        </div>
      </div>
    </div>
  );
}

// Appearance Settings
function AppearanceSettings() {
  const { theme, setTheme } = useThemeStore();

  const themes: { key: 'light' | 'dark' | 'system'; label: string; icon: React.ElementType }[] = [
    { key: 'light', label: 'Light', icon: Sun },
    { key: 'dark', label: 'Dark', icon: Moon },
    { key: 'system', label: 'System', icon: Monitor },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Appearance</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Customize how Tracky PM looks on your device
        </p>
      </div>

      {/* Theme Selection */}
      <Card className="p-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Theme
        </h3>
        <div className="grid grid-cols-3 gap-4">
          {themes.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTheme(key)}
              className={cn(
                'flex flex-col items-center gap-3 p-4 rounded-xl border-2 transition-all',
                theme === key
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
              )}
            >
              <div
                className={cn(
                  'w-12 h-12 rounded-full flex items-center justify-center',
                  theme === key
                    ? 'bg-blue-100 dark:bg-blue-900/50'
                    : 'bg-gray-100 dark:bg-gray-800'
                )}
              >
                <Icon
                  className={cn(
                    'w-6 h-6',
                    theme === key ? 'text-blue-600' : 'text-gray-600 dark:text-gray-400'
                  )}
                />
              </div>
              <span
                className={cn(
                  'text-sm font-medium',
                  theme === key ? 'text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-gray-300'
                )}
              >
                {label}
              </span>
              {theme === key && (
                <Check className="w-4 h-4 text-blue-600" />
              )}
            </button>
          ))}
        </div>
      </Card>

      {/* Accent Color */}
      <Card className="p-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Accent Color
        </h3>
        <div className="flex gap-3">
          {[
            'bg-blue-500',
            'bg-purple-500',
            'bg-green-500',
            'bg-orange-500',
            'bg-pink-500',
            'bg-cyan-500',
          ].map((color, i) => (
            <button
              key={i}
              className={cn(
                'w-8 h-8 rounded-full ring-2 ring-offset-2 ring-offset-white dark:ring-offset-gray-900 transition-transform hover:scale-110',
                color,
                i === 0 ? 'ring-blue-500' : 'ring-transparent'
              )}
            />
          ))}
        </div>
      </Card>

      {/* Compact Mode */}
      <Card className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Compact Mode
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Reduce spacing for more information density
            </p>
          </div>
          <Toggle enabled={false} />
        </div>
      </Card>
    </div>
  );
}

// Notification Settings
function NotificationSettings() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Notifications</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Configure how you receive notifications
        </p>
      </div>

      <Card className="p-6 space-y-6">
        <SettingRow
          title="Import Completion"
          description="Get notified when a file import completes"
          enabled={true}
        />
        <SettingRow
          title="Validation Errors"
          description="Alert when validation errors are detected"
          enabled={true}
        />
        <SettingRow
          title="Resource Overallocation"
          description="Warn when resources exceed 100% utilization"
          enabled={true}
        />
        <SettingRow
          title="Schedule Delays"
          description="Notify when tasks exceed baseline dates"
          enabled={false}
        />
        <SettingRow
          title="System Updates"
          description="Receive updates about new features"
          enabled={true}
        />
      </Card>
    </div>
  );
}

// Data Settings
function DataSettings() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Data & Import</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Configure import behavior and data management
        </p>
      </div>

      {/* Import Defaults */}
      <Card className="p-6 space-y-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Import Defaults
        </h3>
        
        <SettingRow
          title="Auto-validate on Upload"
          description="Automatically validate files before import"
          enabled={true}
        />
        <SettingRow
          title="Smart Merge"
          description="Use intelligent merging for duplicate detection"
          enabled={true}
        />
        <SettingRow
          title="Auto-recalculate Dependencies"
          description="Recalculate schedules after import"
          enabled={true}
        />
      </Card>

      {/* Noise Threshold */}
      <Card className="p-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Noise Threshold
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Ignore schedule changes smaller than this value (in days)
        </p>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min="0"
            max="14"
            defaultValue="3"
            className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
          />
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100 w-16 text-right">
            3 days
          </span>
        </div>
      </Card>

      {/* Data Retention */}
      <Card className="p-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Data Retention
        </h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600 dark:text-gray-400">Audit logs</span>
            <select className="bg-gray-100 dark:bg-gray-800 border-0 rounded-lg text-sm px-3 py-1.5">
              <option>30 days</option>
              <option>90 days</option>
              <option>1 year</option>
              <option>Forever</option>
            </select>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600 dark:text-gray-400">Baseline versions</span>
            <select className="bg-gray-100 dark:bg-gray-800 border-0 rounded-lg text-sm px-3 py-1.5">
              <option>10 versions</option>
              <option>25 versions</option>
              <option>50 versions</option>
              <option>All</option>
            </select>
          </div>
        </div>
      </Card>
    </div>
  );
}

// Security Settings
function SecuritySettings() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Security</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Manage your security preferences
        </p>
      </div>

      <Card className="p-6 space-y-6">
        <SettingRow
          title="Two-Factor Authentication"
          description="Add an extra layer of security to your account"
          enabled={false}
          badge="Recommended"
        />
        <SettingRow
          title="Session Timeout"
          description="Auto-logout after period of inactivity"
          enabled={true}
        />
        <SettingRow
          title="Login Notifications"
          description="Get notified of new login attempts"
          enabled={true}
        />
      </Card>

      {/* Active Sessions */}
      <Card className="p-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Active Sessions
        </h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center">
                <Monitor className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  Current Session
                </p>
                <p className="text-xs text-gray-500">Windows • Chrome</p>
              </div>
            </div>
            <Badge variant="success" size="sm">Active</Badge>
          </div>
        </div>
      </Card>
    </div>
  );
}

// About Section
function AboutSection() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">About</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Information about Tracky PM
        </p>
      </div>

      <Card className="p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center">
            <span className="text-2xl font-bold text-white">T</span>
          </div>
          <div>
            <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              Tracky PM
            </h3>
            <p className="text-sm text-gray-500">Project Management System</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <label className="text-gray-500 dark:text-gray-400">Version</label>
            <p className="font-medium text-gray-900 dark:text-gray-100">1.0.0</p>
          </div>
          <div>
            <label className="text-gray-500 dark:text-gray-400">Build</label>
            <p className="font-medium text-gray-900 dark:text-gray-100">2024.01.15</p>
          </div>
          <div>
            <label className="text-gray-500 dark:text-gray-400">Environment</label>
            <p className="font-medium text-gray-900 dark:text-gray-100">Production</p>
          </div>
          <div>
            <label className="text-gray-500 dark:text-gray-400">API</label>
            <p className="font-medium text-gray-900 dark:text-gray-100">v1</p>
          </div>
        </div>
      </Card>

      {/* Features */}
      <Card className="p-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Features
        </h3>
        <div className="space-y-3">
          {[
            'Smart Merge Import Engine',
            'Real-time Schedule Recalculation',
            'Resource Utilization Tracking',
            'Baseline Version Management',
            'Impact Analysis & Flagging',
            'Comprehensive Audit Logging',
          ].map((feature, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <Check className="w-4 h-4 text-green-500" />
              {feature}
            </div>
          ))}
        </div>
      </Card>

      {/* Legal */}
      <Card className="p-6">
        <div className="flex items-center justify-between text-sm">
          <a href="#" className="text-blue-600 hover:underline">Privacy Policy</a>
          <a href="#" className="text-blue-600 hover:underline">Terms of Service</a>
          <a href="#" className="text-blue-600 hover:underline">Licenses</a>
        </div>
      </Card>
    </div>
  );
}

// Helper Components
interface SettingRowProps {
  title: string;
  description: string;
  enabled: boolean;
  badge?: string;
}

function SettingRow({ title, description, enabled, badge }: SettingRowProps) {
  const [isEnabled, setIsEnabled] = useState(enabled);

  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">{title}</h4>
          {badge && (
            <Badge variant="warning" size="sm">{badge}</Badge>
          )}
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
      </div>
      <Toggle enabled={isEnabled} onChange={setIsEnabled} />
    </div>
  );
}

interface ToggleProps {
  enabled: boolean;
  onChange?: (enabled: boolean) => void;
}

function Toggle({ enabled, onChange }: ToggleProps) {
  return (
    <button
      onClick={() => onChange?.(!enabled)}
      className={cn(
        'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
        enabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'
      )}
    >
      <span
        className={cn(
          'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
          enabled ? 'translate-x-6' : 'translate-x-1'
        )}
      />
    </button>
  );
}
