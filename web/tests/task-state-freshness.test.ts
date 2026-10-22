import {expect,it} from 'vitest'
import {mergeVideoTaskPair} from '../src/lib/store'

it('retains the latest timestamp across multiple out-of-order video responses',()=>{
 const current={id:'one',status:'success',progress:100,message:'Complete',updated_at:'2026-10-22T10:00:10Z'} as any
 const older={...current,status:'summarizing',progress:80,message:'Writing',updated_at:'2026-10-22T10:00:05Z'}
 const middle={...older,progress:90,updated_at:'2026-10-22T10:00:07Z'}
 const once=mergeVideoTaskPair(current,older)
 expect(once.updated_at).toBe(current.updated_at)
 const twice=mergeVideoTaskPair(once,middle)
 expect(twice).toMatchObject(current)
})

it('accepts a genuinely newer retry after a terminal state',()=>{
 const current={id:'one',status:'success',progress:100,updated_at:'2026-10-22T10:00:10Z'} as any
 expect(mergeVideoTaskPair(current,{...current,status:'pending',progress:0,updated_at:'2026-10-22T10:00:11Z'})).toMatchObject({status:'pending',progress:0,updated_at:'2026-10-22T10:00:11Z'})
})
