// @vitest-environment jsdom
import {expect,it} from 'vitest'
import {bufferResponse} from '../src/lib/requestDeadline'

it('preserves every archive byte while buffering an authenticated response',async()=>{
 const bytes=new Uint8Array([0x50,0x4b,3,4,0xff,0x80,0,0xc3,0x28,0x7f])
 const response=await bufferResponse(new Response(bytes,{headers:{'Content-Type':'application/zip','X-Missing-Images':'2'}}))
 expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes)
 expect(response.headers.get('X-Missing-Images')).toBe('2')
})
