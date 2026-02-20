import { Check, Loader2 } from 'lucide-react'

const STEPS = [
  { key: 'parsing', label: 'Parsing', range: [0, 10] },
  { key: 'downloading', label: 'Downloading', range: [10, 30] },
  { key: 'transcribing', label: 'Transcribing', range: [30, 60] },
  { key: 'summarizing', label: 'Generating', range: [60, 92] },
  { key: 'success', label: 'Done', range: [92, 100] },
]

const STEP_ORDER = STEPS.map(s => s.key)

interface Props {
  currentStatus: string
  progress?: number
}

export default function StepBar({ currentStatus, progress = 0 }: Props) {
  const currentIdx = STEP_ORDER.indexOf(currentStatus)
  const effectiveIdx = currentStatus === 'saving' ? 3 : currentIdx

  return (
    <div className="flex items-center px-2">
      {STEPS.map((step, idx) => {
        const isCompleted = effectiveIdx > idx || currentStatus === 'success'
        const isCurrent = idx === effectiveIdx && currentStatus !== 'success'

        let connectorFill = 0
        if (idx < STEPS.length - 1) {
          if (isCompleted) {
            connectorFill = 100
          } else if (isCurrent) {
            const [lo, hi] = step.range
            connectorFill = Math.min(100, Math.max(0, ((progress - lo) / (hi - lo)) * 100))
          }
        }

        return (
          <div key={step.key} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
                  isCompleted
                    ? 'bg-green-600 text-white'
                    : isCurrent
                    ? 'bg-indigo-600 text-white'
                    : 'bg-dark-hover text-gray-500 border border-dark-border'
                }`}
                style={{ transition: 'background-color 0.5s ease' }}
              >
                {isCompleted ? (
                  <Check size={14} />
                ) : isCurrent ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  idx + 1
                )}
              </div>
              <span
                className={`text-[10px] mt-1 whitespace-nowrap ${
                  isCompleted || isCurrent ? 'text-gray-300' : 'text-gray-600'
                }`}
              >
                {step.label}
              </span>
            </div>
            {idx < STEPS.length - 1 && (
              <div className="flex-1 h-0.5 mx-1.5 bg-dark-border rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${connectorFill}%`,
                    backgroundColor: isCompleted ? '#16a34a' : '#6366f1',
                    transition: 'width 1s ease-out, background-color 0.5s ease',
                  }}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
