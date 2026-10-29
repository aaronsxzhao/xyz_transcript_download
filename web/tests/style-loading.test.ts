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

it('shares pending loads and retries after failure instead of caching rejection',async()=>{
 const {retryableStyleLoad}=await import('../src/lib/styleLoading')
 const loader=vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValue('loaded')
 const load=retryableStyleLoad(loader)
 const first=load()
 expect(load()).toBe(first)
 await expect(first).rejects.toThrow('network')
 await expect(load()).resolves.toBe('loaded')
 await expect(load()).resolves.toBe('loaded')
 expect(loader).toHaveBeenCalledTimes(2)
})
it('allows a retry after a timed-out load and ignores late completion of the old load',async()=>{
 vi.useFakeTimers()
 const {retryableStyleLoad}=await import('../src/lib/styleLoading')
 let complete!:(value:unknown)=>void
 const loader=vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve})).mockResolvedValue('new')
 const load=retryableStyleLoad(loader)
 const rejected=expect(load()).rejects.toThrow('timed out')
 await vi.advanceTimersByTimeAsync(8000);await rejected
 await expect(load()).resolves.toBe('new')
 complete('old');await Promise.resolve()
 await expect(load()).resolves.toBe('new')
 expect(loader).toHaveBeenCalledTimes(2)
})
