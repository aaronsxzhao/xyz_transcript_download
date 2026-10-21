// @vitest-environment jsdom
import {beforeEach,expect,it} from 'vitest'
import {clearCache,getCache,setCache,invalidateForMutation} from '../src/lib/cache'
beforeEach(()=>{localStorage.clear();sessionStorage.clear();clearCache()})
it('keeps bulky bodies out of synchronous localStorage and bounds entry count',()=>{
  for(let i=0;i<100;i++)setCache(`summary_${i}`,{text:'A note '.repeat(100)})
  expect(Object.keys(localStorage).filter(key=>key.startsWith('xyz_cache_'))).toEqual([])
  expect(getCache('summary_0')).toBeNull()
  expect(getCache('summary_99')).not.toBeNull()
})
it('bounds bytes and invalidates only related content',()=>{
  setCache('summary_oversized','x'.repeat(2*1024*1024))
  expect(getCache('summary_oversized')).toBeNull()
  setCache('summary_a','Podcast');setCache('video_note_b','Video')
  invalidateForMutation('/api/video-notes/tasks/b')
  expect(getCache('video_note_b')).toBeNull()
  expect(getCache('summary_a')).toBe('Podcast')
})
