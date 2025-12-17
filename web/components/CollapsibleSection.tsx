'use client';

import { useState, useEffect } from 'react';
import { ChevronDown, Check, Lock, Loader2 } from 'lucide-react';

export type SectionStatus = 'completed' | 'current' | 'upcoming' | 'locked' | 'in_progress';

interface CollapsibleSectionProps {
  title: string;
  stepNumber: number;
  status: SectionStatus;
  children: React.ReactNode;
  summary?: React.ReactNode;
  onToggle?: (expanded: boolean) => void;
  forceExpanded?: boolean;
}

export function CollapsibleSection({
  title,
  stepNumber,
  status,
  children,
  summary,
  onToggle,
  forceExpanded,
}: CollapsibleSectionProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Auto-expand based on status
  useEffect(() => {
    if (forceExpanded !== undefined) {
      setIsExpanded(forceExpanded);
    } else if (status === 'current' || status === 'in_progress') {
      setIsExpanded(true);
    } else {
      setIsExpanded(false);
    }
  }, [status, forceExpanded]);

  const handleToggle = () => {
    if (status === 'locked') return;
    const newState = !isExpanded;
    setIsExpanded(newState);
    onToggle?.(newState);
  };

  const statusConfig = {
    completed: {
      icon: <Check className="w-4 h-4" />,
      bg: 'bg-green-500',
      border: 'border-green-200 dark:border-green-800',
      headerBg: 'bg-green-50 dark:bg-green-900/20',
      text: 'text-green-700 dark:text-green-300',
    },
    current: {
      icon: <span className="w-2 h-2 bg-white rounded-full" />,
      bg: 'bg-blue-500',
      border: 'border-blue-200 dark:border-blue-800',
      headerBg: 'bg-blue-50 dark:bg-blue-900/20',
      text: 'text-blue-700 dark:text-blue-300',
    },
    in_progress: {
      icon: <Loader2 className="w-4 h-4 animate-spin" />,
      bg: 'bg-purple-500',
      border: 'border-purple-200 dark:border-purple-800',
      headerBg: 'bg-purple-50 dark:bg-purple-900/20',
      text: 'text-purple-700 dark:text-purple-300',
    },
    upcoming: {
      icon: <span className="text-xs font-bold">{stepNumber}</span>,
      bg: 'bg-gray-300 dark:bg-gray-600',
      border: 'border-gray-200 dark:border-gray-700',
      headerBg: 'bg-gray-50 dark:bg-gray-800/50',
      text: 'text-gray-500 dark:text-gray-400',
    },
    locked: {
      icon: <Lock className="w-3.5 h-3.5" />,
      bg: 'bg-gray-300 dark:bg-gray-600',
      border: 'border-gray-200 dark:border-gray-700',
      headerBg: 'bg-gray-50 dark:bg-gray-800/50',
      text: 'text-gray-400 dark:text-gray-500',
    },
  };

  const config = statusConfig[status];

  return (
    <div className={`border rounded-lg overflow-hidden ${config.border} mb-4`}>
      {/* Header */}
      <button
        onClick={handleToggle}
        disabled={status === 'locked'}
        className={`w-full px-4 py-3 flex items-center gap-3 ${config.headerBg} ${
          status === 'locked' ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:opacity-90'
        } transition-all`}
      >
        {/* Step indicator */}
        <div
          className={`w-7 h-7 rounded-full flex items-center justify-center text-white ${config.bg}`}
        >
          {config.icon}
        </div>

        {/* Title */}
        <div className="flex-1 text-left">
          <h3 className={`font-semibold ${config.text}`}>
            {title}
          </h3>
          {/* Summary when collapsed */}
          {!isExpanded && summary && (
            <div className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {summary}
            </div>
          )}
        </div>

        {/* Status badge */}
        {status === 'current' && (
          <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded-full">
            Next
          </span>
        )}
        {status === 'in_progress' && (
          <span className="px-2 py-0.5 text-xs font-medium bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 rounded-full">
            Running
          </span>
        )}
        {status === 'locked' && (
          <span className="text-xs text-gray-400">Complete previous step</span>
        )}

        {/* Chevron */}
        {status !== 'locked' && (
          <ChevronDown
            className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${
              isExpanded ? 'rotate-180' : ''
            }`}
          />
        )}
      </button>

      {/* Content */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isExpanded ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          {children}
        </div>
      </div>
    </div>
  );
}
