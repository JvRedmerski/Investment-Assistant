import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Join class names, letting a later Tailwind class win over an earlier
 * one in the same group.
 *
 * Without the merge, `cn('p-2', 'p-4')` emits both and the winner
 * depends on stylesheet order rather than on the call.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
