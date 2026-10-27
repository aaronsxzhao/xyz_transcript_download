/**
 * Toast notification system
 */
import { useState, useEffect, useRef, createContext, useContext, ReactNode, useCallback } from 'react'
import {getAuthGeneration} from '../lib/auth'
import { X, CheckCircle, AlertCircle, Info, Loader2 } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'info' | 'loading'

interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
  duration?: number // 0 = persistent
}

interface ToastContextType {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => string
  removeToast: (id: string) => void
  updateToast: (id: string, updates: Partial<Omit<Toast, 'id'>>) => void
}

const ToastContext = createContext<ToastContextType | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())
  const active = useRef(true)
  const records = useRef(new Map<string, Toast>())
  const schedule = (toast: Toast) => {
    clearTimeout(timers.current.get(toast.id))
    timers.current.delete(toast.id)
    const duration = toast.duration ?? (toast.type === 'loading' ? 0 : 5000)
    if (duration > 0) timers.current.set(toast.id, setTimeout(() => {
      timers.current.delete(toast.id)
      records.current.delete(toast.id)
      setToasts(prev => prev.filter(t => t.id !== toast.id))
    }, duration))
  }
  const generation = getAuthGeneration()
  useEffect(() => {
    active.current = true
    const clear = () => {
      timers.current.forEach(clearTimeout)
      timers.current.clear()
      records.current.clear()
      setToasts([])
    }
    window.addEventListener('xyz:session-changed', clear)
    if (generation !== getAuthGeneration()) clear()
    return () => {
      active.current = false
      window.removeEventListener('xyz:session-changed', clear)
      timers.current.forEach(clearTimeout)
      timers.current.clear()
      records.current.clear()
    }
  }, [])

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    if (!active.current || generation !== getAuthGeneration()) return ''
    const id = Math.random().toString(36).substring(7)
    const newToast: Toast = { ...toast, id }
    setToasts((prev) => [...prev, newToast])

    records.current.set(id, newToast)
    schedule(newToast)

    return id
  }, [generation])

  const removeToast = useCallback((id: string) => {
    if (!active.current || generation !== getAuthGeneration()) return
    clearTimeout(timers.current.get(id))
    timers.current.delete(id)
    records.current.delete(id)
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [generation])

  const updateToast = useCallback((id: string, updates: Partial<Omit<Toast, 'id'>>) => {
    if (!active.current || generation !== getAuthGeneration()) return
    const current = records.current.get(id)
    if (!current) return
    const changedType = updates.type !== undefined && updates.type !== current.type
    const next = { ...current, ...updates }
    // Each new status gets its own lifetime; a loading toast's duration=0
    // must not make its later success/failure permanent. Text updates keep it.
    if (changedType && updates.duration === undefined) delete next.duration
    records.current.set(id, next)
    if (changedType || updates.duration !== undefined) schedule(next)
    setToasts(prev => prev.map(t => t.id === id ? next : t))
  }, [generation])

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, updateToast }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

function ToastContainer({ toasts, removeToast }: { toasts: Toast[]; removeToast: (id: string) => void }) {
  return (
    <div className="toast-stack fixed top-20 right-4 z-[90] flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
      ))}
    </div>
  )
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const icons = {
    success: <CheckCircle className="w-5 h-5 text-green-400" />,
    error: <AlertCircle className="w-5 h-5 text-red-400" />,
    info: <Info className="w-5 h-5 text-blue-400" />,
    loading: <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />,
  }

  const bgColors = {
    success: 'border-green-500/30 bg-green-500/10',
    error: 'border-red-500/30 bg-red-500/10',
    info: 'border-blue-500/30 bg-blue-500/10',
    loading: 'border-indigo-500/30 bg-indigo-500/10',
  }

  return (
    <div
      role={toast.type === 'error' ? 'alert' : 'status'}
      className={`flex items-start gap-3 p-4 rounded-lg border ${bgColors[toast.type]} backdrop-blur-sm shadow-lg animate-slide-in`}
    >
      {icons[toast.type]}
      <div className="flex-1 min-w-0">
        <p className="font-medium text-white">{toast.title}</p>
        {toast.message && (
          <p className="text-sm text-gray-400 mt-0.5">{toast.message}</p>
        )}
      </div>
      <button
        onClick={onClose}
        aria-label={`Dismiss notification: ${toast.title}`}
        className="text-gray-500 hover:text-white transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
