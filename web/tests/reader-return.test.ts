import {it,expect} from 'vitest'
import {readerOrigin} from '../src/lib/readerReturn'
it('retains allowed entry paths and filters without allowing reader loops or external returns',()=>{
 for(const path of ['/','/library?q=test&kind=podcast','/videos?channel=abc','/podcasts/show/episodes'])expect(readerOrigin(path)).toBe(path)
 for(const path of ['//evil.test','https://evil.test','/viewer/one','/videos/one','/login',null])expect(readerOrigin(path)).toBeNull()
})
