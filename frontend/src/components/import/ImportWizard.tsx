/**
 * Import Wizard - 3-step flow for Excel import
 * Step 1: Upload → Step 2: Validate → Step 3: Execute
 */
import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload,
  FileCheck,
  PlayCircle,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  X,
  Settings2,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import {
  useImportWizardStore,
  type ImportWizardStep,
} from '../../stores';
import { useValidateExcel, useImportExcel } from '../../lib/queries';
import { useToast } from '../ui/Toast';
import { Button, Modal, Card } from '../ui';
import { FileDropzone } from './FileDropzone';
import { ValidationPreview } from './ValidationPreview';
import { ImportResults } from './ImportResults';

const steps: {
  id: ImportWizardStep;
  title: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    id: 'upload',
    title: 'Upload File',
    description: 'Select your Excel file',
    icon: <Upload className="h-5 w-5" />,
  },
  {
    id: 'validate',
    title: 'Validate',
    description: 'Review parsed data',
    icon: <FileCheck className="h-5 w-5" />,
  },
  {
    id: 'execute',
    title: 'Import',
    description: 'Execute the import',
    icon: <PlayCircle className="h-5 w-5" />,
  },
  {
    id: 'complete',
    title: 'Complete',
    description: 'View results',
    icon: <CheckCircle2 className="h-5 w-5" />,
  },
];

interface ImportWizardProps {
  onComplete?: () => void;
  onCancel?: () => void;
}

export function ImportWizard({ onComplete, onCancel }: ImportWizardProps = {}) {
  const {
    isOpen,
    closeWizard,
    currentStep,
    setStep,
    selectedFile,
    setFile,
    validationResult,
    setValidationResult,
    importResult,
    setImportResult,
    importOptions,
    setImportOption,
    reset,
  } = useImportWizardStore();

  const [showOptions, setShowOptions] = useState(false);
  const { success, error: showError } = useToast();

  // Mutations
  const validateMutation = useValidateExcel({
    onSuccess: (data) => {
      setValidationResult(data);
      setStep('validate');
    },
    onError: (err) => {
      showError('Validation Failed', err.message);
    },
  });

  const importMutation = useImportExcel({
    onSuccess: (data) => {
      setImportResult(data);
      setStep('complete');
      if (data.status === 'success') {
        success('Import Successful', `Processed ${data.summary.tasks_created + data.summary.tasks_updated} work items`);
      }
    },
    onError: (err) => {
      showError('Import Failed', err.message);
    },
  });

  // Handlers
  const handleFileSelect = useCallback(
    (file: File) => {
      setFile(file);
    },
    [setFile]
  );

  const handleValidate = useCallback(() => {
    if (selectedFile) {
      validateMutation.mutate(selectedFile);
    }
  }, [selectedFile, validateMutation]);

  const handleImport = useCallback(() => {
    if (selectedFile) {
      importMutation.mutate({
        file: selectedFile,
        options: importOptions,
      });
    }
  }, [selectedFile, importOptions, importMutation]);

  const handleClose = useCallback(() => {
    closeWizard();
    onCancel?.();
    // Reset after animation completes
    setTimeout(reset, 300);
  }, [closeWizard, reset, onCancel]);

  const handleFinish = useCallback(() => {
    closeWizard();
    onComplete?.();
    // Reset after animation completes
    setTimeout(reset, 300);
  }, [closeWizard, reset, onComplete]);

  const handleBack = useCallback(() => {
    if (currentStep === 'validate') {
      setStep('upload');
    } else if (currentStep === 'execute') {
      setStep('validate');
    }
  }, [currentStep, setStep]);

  const handleNext = useCallback(() => {
    if (currentStep === 'upload' && selectedFile) {
      handleValidate();
    } else if (currentStep === 'validate' && validationResult?.valid) {
      setStep('execute');
    } else if (currentStep === 'execute') {
      handleImport();
    }
  }, [currentStep, selectedFile, validationResult, handleValidate, handleImport, setStep]);

  // Get current step index
  const currentStepIndex = steps.findIndex((s) => s.id === currentStep);

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      size="full"
      showCloseButton={false}
    >
      <div className="min-h-[600px] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-gray-200 dark:border-gray-800">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Import Excel File
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Follow the steps to import your project data
            </p>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={handleClose}>
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Progress Steps */}
        <div className="flex items-center justify-center py-6 border-b border-gray-100 dark:border-gray-800">
          {steps.map((step, index) => {
            const isActive = step.id === currentStep;
            const isCompleted = index < currentStepIndex;

            return (
              <div key={step.id} className="flex items-center">
                <div className="flex flex-col items-center">
                  <motion.div
                    className={cn(
                      'flex items-center justify-center w-10 h-10 rounded-full transition-all',
                      isActive
                        ? 'bg-brand-500 text-white shadow-glow'
                        : isCompleted
                        ? 'bg-green-500 text-white'
                        : 'bg-gray-100 text-gray-400 dark:bg-gray-800'
                    )}
                    animate={isActive ? { scale: [1, 1.1, 1] } : {}}
                    transition={{ duration: 0.3 }}
                  >
                    {isCompleted ? (
                      <CheckCircle2 className="h-5 w-5" />
                    ) : (
                      step.icon
                    )}
                  </motion.div>
                  <p
                    className={cn(
                      'mt-2 text-xs font-medium',
                      isActive
                        ? 'text-brand-600 dark:text-brand-400'
                        : isCompleted
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-gray-500 dark:text-gray-400'
                    )}
                  >
                    {step.title}
                  </p>
                </div>
                {index < steps.length - 1 && (
                  <div
                    className={cn(
                      'w-16 h-0.5 mx-2 transition-all',
                      index < currentStepIndex
                        ? 'bg-green-500'
                        : 'bg-gray-200 dark:bg-gray-700'
                    )}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Content */}
        <div className="flex-1 py-6 overflow-y-auto">
          <AnimatePresence mode="wait">
            {currentStep === 'upload' && (
              <motion.div
                key="upload"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <div className="max-w-xl mx-auto">
                  <FileDropzone
                    onFileSelect={handleFileSelect}
                    selectedFile={selectedFile}
                    onClear={() => setFile(null)}
                    isLoading={validateMutation.isPending}
                    error={validateMutation.error?.message}
                  />

                  {/* Import Options */}
                  <div className="mt-6">
                    <button
                      onClick={() => setShowOptions(!showOptions)}
                      className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                    >
                      <Settings2 className="h-4 w-4" />
                      <span>Import Options</span>
                      <ChevronRight
                        className={cn(
                          'h-4 w-4 transition-transform',
                          showOptions && 'rotate-90'
                        )}
                      />
                    </button>

                    <AnimatePresence>
                      {showOptions && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <Card className="mt-3 p-4 space-y-3">
                            <OptionToggle
                              label="Ghost Check"
                              description="Cancel tasks missing from Excel"
                              checked={importOptions.performGhostCheck}
                              onChange={(v) => setImportOption('performGhostCheck', v)}
                            />
                            <OptionToggle
                              label="Recalculation"
                              description="Trigger date propagation after import"
                              checked={importOptions.triggerRecalculation}
                              onChange={(v) => setImportOption('triggerRecalculation', v)}
                            />
                            <OptionToggle
                              label="Baseline Version"
                              description="Save baseline snapshot before import"
                              checked={importOptions.saveBaselineVersion}
                              onChange={(v) => setImportOption('saveBaselineVersion', v)}
                            />
                            <OptionToggle
                              label="Dry Run"
                              description="Validate only, don't commit changes"
                              checked={importOptions.dryRun}
                              onChange={(v) => setImportOption('dryRun', v)}
                            />
                          </Card>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </motion.div>
            )}

            {currentStep === 'validate' && validationResult && (
              <motion.div
                key="validate"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <ValidationPreview
                  result={validationResult}
                  fileName={selectedFile?.name || 'Unknown'}
                />
              </motion.div>
            )}

            {currentStep === 'execute' && (
              <motion.div
                key="execute"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="max-w-xl mx-auto text-center py-8"
              >
                <div className="p-6 rounded-2xl bg-brand-50 dark:bg-brand-900/20 mb-6">
                  <PlayCircle className="h-16 w-16 text-brand-500 mx-auto mb-4" />
                  <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Ready to Import
                  </h3>
                  <p className="mt-2 text-gray-600 dark:text-gray-400">
                    Click the button below to start the import process.
                    This will sync your Excel data with the database.
                  </p>
                </div>

                <div className="text-left bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                    Import Configuration
                  </h4>
                  <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      Ghost Check: {importOptions.performGhostCheck ? 'Enabled' : 'Disabled'}
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      Recalculation: {importOptions.triggerRecalculation ? 'Enabled' : 'Disabled'}
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      Baseline Versioning: {importOptions.saveBaselineVersion ? 'Enabled' : 'Disabled'}
                    </li>
                    {importOptions.dryRun && (
                      <li className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                        <CheckCircle2 className="h-4 w-4" />
                        DRY RUN MODE - No changes will be saved
                      </li>
                    )}
                  </ul>
                </div>
              </motion.div>
            )}

            {currentStep === 'complete' && importResult && (
              <motion.div
                key="complete"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <ImportResults result={importResult} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-gray-200 dark:border-gray-800">
          <div>
            {currentStep !== 'upload' && currentStep !== 'complete' && (
              <Button
                variant="ghost"
                onClick={handleBack}
                disabled={validateMutation.isPending || importMutation.isPending}
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </Button>
            )}
          </div>

          <div className="flex gap-3">
            {currentStep === 'complete' ? (
              <Button onClick={handleFinish}>
                Done
              </Button>
            ) : (
              <>
                <Button variant="ghost" onClick={handleClose}>
                  Cancel
                </Button>
                <Button
                  onClick={handleNext}
                  disabled={
                    (currentStep === 'upload' && !selectedFile) ||
                    (currentStep === 'validate' && !validationResult?.valid) ||
                    validateMutation.isPending ||
                    importMutation.isPending
                  }
                  isLoading={validateMutation.isPending || importMutation.isPending}
                >
                  {currentStep === 'upload' && 'Validate'}
                  {currentStep === 'validate' && 'Continue'}
                  {currentStep === 'execute' && (importOptions.dryRun ? 'Run Dry Import' : 'Start Import')}
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}

// Option Toggle Component
function OptionToggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between cursor-pointer group">
      <div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-white">
          {label}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
      </div>
      <div
        className={cn(
          'relative w-11 h-6 rounded-full transition-colors',
          checked ? 'bg-brand-500' : 'bg-gray-200 dark:bg-gray-700'
        )}
        onClick={() => onChange(!checked)}
      >
        <div
          className={cn(
            'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform shadow-sm',
            checked ? 'translate-x-6' : 'translate-x-1'
          )}
        />
      </div>
    </label>
  );
}
