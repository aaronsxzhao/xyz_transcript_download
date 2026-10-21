import {expect,it} from 'vitest'
import {artworkUrl} from '../src/lib/artwork'
it('uses persistent proxy for public covers and keeps private signature intact',()=>{
  expect(artworkUrl('https://bts-image.xyzcdn.net/cover.jpg')).toBe('/api/image-proxy?url=https%3A%2F%2Fbts-image.xyzcdn.net%2Fcover.jpg&v=2')
  expect(artworkUrl('/data/thumbnails/owned.jpg?expires=10&signature=valid')).toBe('/data/thumbnails/owned.jpg?expires=10&signature=valid&preview=true')
  expect(artworkUrl('javascript:alert(1)')).toBe('')
  expect(artworkUrl('//attacker.invalid/image.jpg')).toBe('')
})
