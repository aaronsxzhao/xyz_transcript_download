import { useContext } from 'react'
import { ConnectionNoticeContext, isConnectionError, retryConnection, useConnectionRecovery } from '../lib/connectionRecovery'
export default function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  const connection = isConnectionError(message)
  const sharedNotice = useContext(ConnectionNoticeContext)
  useConnectionRecovery(onRetry, connection)
  if (connection && sharedNotice) return null
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 p-3 border border-red-500/30 bg-red-500/10 rounded-lg text-sm text-red-300">
      <span>{message}</span>
      <button onClick={connection ? retryConnection : onRetry} className="underline font-medium">Retry</button>
    </div>
  )
}
