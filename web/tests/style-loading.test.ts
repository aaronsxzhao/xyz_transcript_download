import {afterEach,expect,it,vi} from 'vitest'
import {withStyleTimeout} from '../src/lib/styleLoading'
afterEach(()=>vi.useRealTimers())
it('bounds a stalled cosmetic request and tolerates its late completion',async()=>{
 vi.useFakeTimers()
 let complete!:()=>void
 const pending=withStyleTimeout(new Promise<void>(resolve=>{complete=resolve}))
 const rejected=expect(pending).rejects.toThrow('timed out')
 await vi.advanceTimersByTimeAsync(8000)
 await rejected
 complete()
 await Promise.resolve()
 expect(vi.getTimerCount()).toBe(0)
})
it('returns successful loads and clears their timer',async()=>{
 vi.useFakeTimers()
 await expect(withStyleTimeout(Promise.resolve('ready'))).resolves.toBe('ready')
 expect(vi.getTimerCount()).toBe(0)
})
