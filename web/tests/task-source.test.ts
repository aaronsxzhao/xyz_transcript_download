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
it.each(['twitter','substack'])('does not send %s public-source failures to nonexistent account settings',platform=>{
 const failure=taskFailure('LOGIN_REQUIRED',platform)
 expect(failure.retryAfterSignIn).toBe(false)
 expect(failure.message).toContain('Open the original link')
 expect(failure.message).not.toContain('Settings')
})

it('keeps Spotify, Apple, local and RSS task sources separate from Xiaoyuzhou',()=>{
 const eid='0123456789abcdef01234567'
 expect(taskSource('','https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ?si=tracking',eid,'podcast')).toMatchObject({name:'Spotify',original:'https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ'})
 expect(taskSource('','https://podcasts.apple.com/podcast/id123?i=456&utm_source=copy',eid,'podcast')).toMatchObject({name:'Apple Podcasts',original:'https://podcasts.apple.com/podcast/id123?i=456'})
 expect(taskSource('','apple://'+eid,eid,'podcast')).toMatchObject({name:'Public RSS',original:''})
 expect(taskSource('','local://'+eid,eid,'podcast')).toMatchObject({name:'Local upload',original:''})
})

it('opens the selected Bilibili part without retaining tracking or invalid part parameters',()=>{
 expect(taskSource('bilibili','https://www.bilibili.com/video/BV1xx411c7mD?p=3&share_source=copy').original).toBe('https://www.bilibili.com/video/BV1xx411c7mD?p=3')
 for(const page of ['0','-1','NaN','1%26tracking%3Dyes'])
  expect(taskSource('bilibili',`https://www.bilibili.com/video/BV1xx411c7mD?p=${page}`).original).toBe('https://www.bilibili.com/video/BV1xx411c7mD')
})
