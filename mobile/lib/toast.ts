import { toast } from 'burnt';

export type ToastKind = 'success' | 'warning' | 'error' | 'info';

interface ShowToastArgs {
  kind: ToastKind;
  message: string;
  title?: string;
  duration?: number;
}

const PRESET_BY_KIND: Record<ToastKind, 'done' | 'error' | 'none'> = {
  success: 'done',
  warning: 'none',
  error: 'error',
  info: 'none',
};

export function showToast({ kind, message, title, duration = 3 }: ShowToastArgs): void {
  toast({
    title: title ?? defaultTitle(kind),
    message,
    preset: PRESET_BY_KIND[kind],
    duration,
    haptic: kind === 'error' ? 'error' : kind === 'success' ? 'success' : 'warning',
  });
}

function defaultTitle(kind: ToastKind): string {
  switch (kind) {
    case 'success':
      return 'Done';
    case 'warning':
      return 'Heads up';
    case 'error':
      return 'Something went wrong';
    case 'info':
      return 'Info';
  }
}
