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

it('accepts authoritative completion over a later client-clock queued placeholder',()=>{
 const placeholder={id:'fast',status:'pending',progress:0,updated_at:'2026-10-26T17:05:00Z',client_pending:true} as any
 const complete={id:'fast',status:'success',progress:100,updated_at:'2026-10-26T17:00:00Z'} as any
 expect(mergeVideoTaskPair(placeholder,complete)).toMatchObject(complete)
})

it('never replaces acknowledged processing or completion with a late queued placeholder',()=>{
 for(const status of ['summarizing','success']){
  const live={id:'fast',status,progress:status==='success'?100:80,updated_at:'2026-10-26T17:00:00Z'} as any
  expect(mergeVideoTaskPair(live,{...live,status:'pending',progress:0,updated_at:'2026-10-26T17:05:00Z',client_pending:true})).toMatchObject(live)
 }
})
