import {expect,it} from 'vitest'
import {taskFailure,taskSource} from '../src/lib/taskSource'
it('distinguishes historical source checks from website login without exposing raw codes',()=>{
 for(const code of ['LOGIN_REQUIRED','COOKIES_REQUIRED','AGE_RESTRICTED']) {
  const failure=taskFailure(code,'youtube')
  expect(failure.message).toContain('YouTube')
  expect(failure.message).toContain('when this task ran')
  expect(failure.retryAfterSignIn).toBe(true)
 }
 expect(taskFailure('Purchase required').retryAfterSignIn).toBe(false)
 expect(taskFailure(undefined).message).toBe('')
})
it('keeps source links platform specific and excludes unsafe links and unrelated query parameters',()=>{
 expect(taskSource('youtube','https://youtu.be/abcdefghijk?secret=hidden').original).toBe('https://www.youtube.com/watch?v=abcdefghijk')
 expect(taskSource('youtube','https://example.com/watch?v=abcdefghijk').original).toBe('')
 expect(taskSource('youtube','javascript:alert(1)').original).toBe('')
 expect(taskSource('youtube','', '0123456789abcdef01234567','video').original).toBe('')
 expect(taskSource('', '', '0123456789abcdef01234567','podcast').original).toContain('xiaoyuzhoufm.com/episode/')
})
