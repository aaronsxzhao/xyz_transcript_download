import { createContext } from 'react'

/** A missing image can open the owning reader's recovery tools. */
export const ScreenshotRecoveryContext = createContext<(() => void) | undefined>(undefined)
