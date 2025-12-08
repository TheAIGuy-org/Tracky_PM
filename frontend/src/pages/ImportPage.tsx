/**
 * Import Page
 * Dedicated page for importing Excel files
 */
import { Upload, FileSpreadsheet, CheckCircle, AlertTriangle } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { useImportWizardStore } from '../stores';
import { ImportWizard } from '../components/import/ImportWizard';

export function ImportPage() {
  const { openWizard, isOpen } = useImportWizardStore();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Import Data
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Import your project schedules from Excel files
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">
          {/* Main Import Card */}
          <Card className="p-8 mb-6">
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center">
                <Upload className="w-8 h-8 text-white" />
              </div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Import Excel Schedule
              </h2>
              <p className="text-gray-500 dark:text-gray-400 mb-6 max-w-md mx-auto">
                Upload your project schedule file to import work items, resources, and dependencies.
                Supports .xlsx and .xls formats.
              </p>
              <Button size="lg" onClick={openWizard}>
                <Upload className="w-5 h-5 mr-2" />
                Start Import
              </Button>
            </div>
          </Card>

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="p-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                  <FileSpreadsheet className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-100">
                    Smart Parsing
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Automatically detects and maps columns from your Excel file
                  </p>
                </div>
              </div>
            </Card>

            <Card className="p-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center flex-shrink-0">
                  <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-100">
                    Validation
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Pre-import validation catches errors before they cause issues
                  </p>
                </div>
              </div>
            </Card>

            <Card className="p-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-100">
                    Smart Merge
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Intelligently merges updates without losing existing data
                  </p>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>

      {/* Import Wizard Modal */}
      {isOpen && <ImportWizard />}
    </div>
  );
}
