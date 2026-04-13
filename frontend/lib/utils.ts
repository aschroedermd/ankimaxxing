import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function scoreColor(score: string): string {
  const map: Record<string, string> = {
    accurate: 'text-green-600 bg-green-50',
    probably_accurate: 'text-blue-600 bg-blue-50',
    possibly_inaccurate: 'text-yellow-600 bg-yellow-50',
    likely_inaccurate: 'text-orange-600 bg-orange-50',
    wrong: 'text-red-600 bg-red-50',
  };
  return map[score] ?? 'text-gray-600 bg-gray-50';
}

export function scoreLabel(score: string): string {
  const map: Record<string, string> = {
    accurate: 'Accurate',
    probably_accurate: 'Probably Accurate',
    possibly_inaccurate: 'Possibly Inaccurate',
    likely_inaccurate: 'Likely Inaccurate',
    wrong: 'Wrong',
  };
  return map[score] ?? score;
}

export function supportLevelColor(level: string): string {
  const map: Record<string, string> = {
    full: 'text-green-700 bg-green-100',
    caution: 'text-yellow-700 bg-yellow-100',
    audit_only: 'text-orange-700 bg-orange-100',
    unsupported: 'text-red-700 bg-red-100',
  };
  return map[level] ?? 'text-gray-700 bg-gray-100';
}

export function statusColor(status: string): string {
  const map: Record<string, string> = {
    pending: 'text-gray-600 bg-gray-100',
    running: 'text-blue-600 bg-blue-100',
    complete: 'text-green-600 bg-green-100',
    failed: 'text-red-600 bg-red-100',
    cancelled: 'text-gray-500 bg-gray-100',
    approved: 'text-green-600 bg-green-100',
    rejected: 'text-red-600 bg-red-100',
    written_back: 'text-purple-600 bg-purple-100',
  };
  return map[status] ?? 'text-gray-600 bg-gray-100';
}

export function formatDate(date: string): string {
  try {
    return new Date(date).toLocaleString();
  } catch {
    return date;
  }
}

export function progressPercent(processed: number, total: number): number {
  if (!total) return 0;
  return Math.round((processed / total) * 100);
}
