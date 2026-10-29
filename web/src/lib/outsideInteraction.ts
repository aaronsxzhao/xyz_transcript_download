import {useEffect} from 'react'

/** Pointer and keyboard focus dismiss disclosures without stealing focus. */
export function useOutsideInteraction(onTarget: (target: Node) => void) {
  useEffect(() => {
    const handle = (event: Event) => { if (event.target instanceof Node) onTarget(event.target) }
    document.addEventListener('pointerdown', handle)
    document.addEventListener('focusin', handle)
    return () => {
      document.removeEventListener('pointerdown', handle)
      document.removeEventListener('focusin', handle)
    }
  }, [onTarget])
}
