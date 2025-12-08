/**
 * File Dropzone component for Excel upload
 */
import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  X,
} from 'lucide-react';
import { cn, formatFileSize, isExcelFile } from '../../lib/utils';
import { Button } from '../ui';

interface FileDropzoneProps {
  onFileSelect: (file: File) => void;
  selectedFile: File | null;
  onClear: () => void;
  error?: string;
  isLoading?: boolean;
}

export function FileDropzone({
  onFileSelect,
  selectedFile,
  onClear,
  error,
  isLoading,
}: FileDropzoneProps) {
  const [dragError, setDragError] = useState<string | null>(null);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: readonly { file: File; errors: readonly { message: string }[] }[]) => {
      setDragError(null);

      if (rejectedFiles.length > 0) {
        setDragError('Please upload a valid Excel file (.xlsx or .xls)');
        return;
      }

      if (acceptedFiles.length > 0) {
        const file = acceptedFiles[0];
        if (!isExcelFile(file)) {
          setDragError('Please upload a valid Excel file (.xlsx or .xls)');
          return;
        }
        onFileSelect(file);
      }
    },
    [onFileSelect]
  );

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    maxFiles: 1,
    disabled: isLoading,
  });

  const displayError = error || dragError;

  return (
    <div className="w-full">
      <AnimatePresence mode="wait">
        {selectedFile ? (
          <motion.div
            key="file-selected"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className={cn(
              'relative rounded-xl border-2 border-dashed p-6',
              'bg-green-50 border-green-300 dark:bg-green-900/20 dark:border-green-700'
            )}
          >
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 p-3 rounded-xl bg-green-100 dark:bg-green-900/30">
                <FileSpreadsheet className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                  <p className="text-sm font-medium text-green-800 dark:text-green-200">
                    File selected
                  </p>
                </div>
                <p className="mt-1 text-sm text-gray-700 dark:text-gray-300 truncate">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {formatFileSize(selectedFile.size)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onClear}
                disabled={isLoading}
                className="flex-shrink-0"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="dropzone"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div
              {...getRootProps()}
              className={cn(
                'relative rounded-xl border-2 border-dashed p-8 transition-all duration-200 cursor-pointer',
                'hover:border-brand-400 hover:bg-brand-50/50 dark:hover:bg-brand-900/10',
                isDragActive && !isDragReject
                  ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20'
                  : 'border-gray-300 dark:border-gray-700',
                isDragReject || displayError
                  ? 'border-red-400 bg-red-50 dark:bg-red-900/20'
                  : '',
                isLoading && 'pointer-events-none opacity-50'
              )}
            >
              <input {...getInputProps()} />

              <div className="flex flex-col items-center text-center">
                <motion.div
                  animate={{
                    y: isDragActive ? -5 : 0,
                    scale: isDragActive ? 1.05 : 1,
                  }}
                  className={cn(
                    'p-4 rounded-2xl mb-4',
                    isDragActive
                      ? 'bg-brand-100 dark:bg-brand-900/30'
                      : 'bg-gray-100 dark:bg-gray-800'
                  )}
                >
                  <Upload
                    className={cn(
                      'h-10 w-10',
                      isDragActive
                        ? 'text-brand-500'
                        : 'text-gray-400 dark:text-gray-500'
                    )}
                  />
                </motion.div>

                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {isDragActive
                    ? 'Drop your Excel file here'
                    : 'Drag and drop your Excel file here'}
                </p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  or{' '}
                  <span className="text-brand-600 dark:text-brand-400 font-medium">
                    browse files
                  </span>
                </p>
                <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
                  Supports .xlsx and .xls files up to 10MB
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {displayError && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-3 flex items-center gap-2 text-sm text-red-600 dark:text-red-400"
        >
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{displayError}</span>
        </motion.div>
      )}
    </div>
  );
}
