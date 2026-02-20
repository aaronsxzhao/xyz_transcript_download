import { useState, useRef, useCallback } from 'react'
import { ExternalLink, Upload, Loader2, CheckCircle, Download } from 'lucide-react'
import { uploadCookieFile, fetchAllCookies } from '../../lib/api'

const EXTENSION_URL = 'https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc'

interface Props {
  compact?: boolean
  onCookiesSaved?: () => void
}

export default function YouTubeCookieGuide({ compact, onCookiesSaved }: Props) {
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(async (file: File) => {
    setUploading(true)
    setMessage('')
    try {
      const result = await uploadCookieFile('youtube', file)
      setMessage(`Done! ${result.cookie_count} cookies saved.`)
      onCookiesSaved?.()
      try {
        await fetchAllCookies()
      } catch {}
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Upload failed. Please try again.')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }, [onCookiesSaved])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  const stepCircle = (n: number) => (
    <span className={`inline-flex items-center justify-center ${compact ? 'w-5 h-5 text-[10px]' : 'w-7 h-7 text-xs'} rounded-full bg-indigo-600 text-white font-bold flex-shrink-0`}>
      {n}
    </span>
  )

  if (compact) {
    return (
      <div className="space-y-3 text-left">
        <p className="text-xs text-gray-400 font-medium">How to get YouTube cookies (4 easy steps):</p>
        <div className="space-y-2">
          <div className="flex items-start gap-2">
            {stepCircle(1)}
            <span className="text-xs text-gray-300">
              Install{' '}
              <a href={EXTENSION_URL} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline">
                this free Chrome extension
              </a>
            </span>
          </div>
          <div className="flex items-start gap-2">
            {stepCircle(2)}
            <span className="text-xs text-gray-300">
              Open{' '}
              <a href="https://www.youtube.com" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline">
                YouTube
              </a>
              {' '}and log in
            </span>
          </div>
          <div className="flex items-start gap-2">
            {stepCircle(3)}
            <span className="text-xs text-gray-300">Click the extension icon → click "Export"</span>
          </div>
          <div className="flex items-start gap-2">
            {stepCircle(4)}
            <span className="text-xs text-gray-300">
              Upload the file in{' '}
              <span className="text-white font-medium">Settings → Platform Accounts → YouTube</span>
            </span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Step 1 */}
      <div className="flex items-start gap-3">
        {stepCircle(1)}
        <div className="flex-1 space-y-2">
          <p className="text-sm text-white font-medium">Get the helper tool</p>
          <p className="text-xs text-gray-400">
            Add a small free tool to your browser. It helps you save your YouTube login so this app can download videos for you.
          </p>
          <a
            href={EXTENSION_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Download size={16} />
            Add to Chrome (free)
            <ExternalLink size={12} className="opacity-60" />
          </a>
          <p className="text-[11px] text-gray-500">
            Using Firefox or Edge?{' '}
            <a href="https://addons.mozilla.org/firefox/addon/cookies-txt/" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">
              Firefox version
            </a>
            {' · '}
            The Chrome version also works in Edge
          </p>
        </div>
      </div>

      {/* Step 2 */}
      <div className="flex items-start gap-3">
        {stepCircle(2)}
        <div className="flex-1 space-y-2">
          <p className="text-sm text-white font-medium">Open YouTube and log in</p>
          <p className="text-xs text-gray-400">
            Make sure you're logged in — you should see your profile picture in the top-right corner.
          </p>
          <a
            href="https://www.youtube.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            ▶️ Open YouTube
            <ExternalLink size={12} className="opacity-60" />
          </a>
        </div>
      </div>

      {/* Step 3 */}
      <div className="flex items-start gap-3">
        {stepCircle(3)}
        <div className="flex-1 space-y-2">
          <p className="text-sm text-white font-medium">Save your cookies</p>
          <div className="p-3 bg-dark-hover rounded-lg border border-dark-border space-y-2">
            <p className="text-xs text-gray-300">
              <span className="text-white font-medium">a.</span> Look for the{' '}
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-gray-700 rounded text-[11px] text-white">🧩 puzzle piece</span>
              {' '}icon at the top-right of your browser
            </p>
            <p className="text-xs text-gray-300">
              <span className="text-white font-medium">b.</span> Click it, then click{' '}
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-gray-700 rounded text-[11px] text-white">🍪 Get cookies.txt LOCALLY</span>
            </p>
            <p className="text-xs text-gray-300">
              <span className="text-white font-medium">c.</span> Click the big{' '}
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-700 rounded text-[11px] text-white">Export</span>
              {' '}button — a file will download to your computer
            </p>
          </div>
        </div>
      </div>

      {/* Step 4 */}
      <div className="flex items-start gap-3">
        {stepCircle(4)}
        <div className="flex-1 space-y-2">
          <p className="text-sm text-white font-medium">Upload the file here</p>
          <p className="text-xs text-gray-400">
            Drag the downloaded file into the box below, or click the box to find it.
          </p>

          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.cookie,.cookies"
            className="hidden"
            onChange={e => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
            }}
          />

          {/* Drop zone */}
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={`relative flex flex-col items-center justify-center gap-2 p-6 border-2 border-dashed rounded-xl cursor-pointer transition-all ${
              dragging
                ? 'border-indigo-400 bg-indigo-600/10'
                : 'border-dark-border hover:border-indigo-500/50 hover:bg-dark-hover/50'
            }`}
          >
            {uploading ? (
              <>
                <Loader2 size={28} className="text-indigo-400 animate-spin" />
                <p className="text-sm text-gray-300">Uploading...</p>
              </>
            ) : (
              <>
                <Upload size={28} className={dragging ? 'text-indigo-400' : 'text-gray-500'} />
                <p className="text-sm text-gray-300 font-medium">
                  {dragging ? 'Drop it here!' : 'Drop cookies file here'}
                </p>
                <p className="text-xs text-gray-500">or click to browse files</p>
              </>
            )}
          </div>

          {/* Result message */}
          {message && (
            <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
              message.startsWith('Done')
                ? 'bg-green-500/10 border border-green-500/30 text-green-400'
                : 'bg-red-500/10 border border-red-500/30 text-red-400'
            }`}>
              {message.startsWith('Done') && <CheckCircle size={16} />}
              {message}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
