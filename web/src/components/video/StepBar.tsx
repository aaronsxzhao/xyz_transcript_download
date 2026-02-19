import { Check, Loader2 } from 'lucide-react'

const STEPS = [
  { key: 'parsing', label: 'Parsing' },
  { key: 'downloading', label: 'Downloading' },
  { key: 'transcribing', label: 'Transcribing' },
  { key: 'summarizing', label: 'Generating' },
  { key: 'success', label: 'Done' },
]

const STEP_ORDER = STEPS.map(s => s.key)

interface Props {
  currentStatus: string
}

export default function StepBar({ currentStatus }: Props) {
  const currentIdx = STEP_ORDER.indexOf(currentStatus)

  return (
    <div className="flex items-center justify-between px-2">
      {STEPS.map((step, idx) => {
        const isCompleted = currentIdx > idx || currentStatus === 'success'
        const isCurrent = currentStatus === step.key || (currentStatus === 'saving' && step.key === 'summarizing')

        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${
                  isCompleted
                    ? 'bg-green-600 text-white'
                    : isCurrent
                    ? 'bg-indigo-600 text-white'
                    : 'bg-dark-hover text-gray-500 border border-dark-border'
                }`}
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
                className={`text-[10px] mt-1 ${
                  isCompleted || isCurrent ? 'text-gray-300' : 'text-gray-600'
                }`}
              >
                {step.label}
              </span>
            </div>
            {idx < STEPS.length - 1 && (
              <div
                className={`w-6 sm:w-10 h-0.5 mx-1 transition-colors ${
                  isCompleted ? 'bg-green-600' : 'bg-dark-border'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
