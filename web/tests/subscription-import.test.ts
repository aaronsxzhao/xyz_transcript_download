// @vitest-environment jsdom
import {beforeEach,expect,it,vi} from 'vitest'
import {importUserSubscriptions} from '../src/lib/api'
import {clearCache} from '../src/lib/cache'

beforeEach(()=>{localStorage.clear();sessionStorage.clear();clearCache();vi.restoreAllMocks()})
it('keeps the profile-data limitation from the API',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'This public page does not expose its subscription list.'}),{status:422,headers:{'Content-Type':'application/json'}})))
 await expect(importUserSubscriptions('0123456789abcdef01234567')).rejects.toThrow('does not expose its subscription list')
})
it('reports gateway HTML without leaking markup or a JSON parser exception',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html>private upstream debug page</html>',{status:502,headers:{'Content-Type':'text/html'}})))
 await expect(importUserSubscriptions('0123456789abcdef01234567')).rejects.toThrow('website gateway returned an error page (HTTP 502)')
})
it('preserves a successful import result',async()=>{
 const result={total_found:2,newly_added:1,already_subscribed:1,failed:0,podcasts:['Fixture show']}
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(result),{status:200,headers:{'Content-Type':'application/json'}})))
 await expect(importUserSubscriptions('0123456789abcdef01234567')).resolves.toEqual(result)
})
