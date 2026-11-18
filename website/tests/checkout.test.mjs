import test from 'node:test'
import assert from 'node:assert/strict'
import {phoneNumber,checkoutErrors,campaignFromSearch} from '../src/checkout.js'

test('Ukrainian checkout phone formats normalize consistently',()=>{
  for(const value of ['0671234567','+38 (067) 123-45-67','380671234567','671234567'])assert.equal(phoneNumber(value),'+380671234567')
  for(const value of ['123','+441234567890','٠٦٧١٢٣٤٥٦٧'])assert.equal(phoneNumber(value),'')
})
test('checkout validates both contact fields and combined database name limit',()=>{
  const form={contact_surname:'Покупець',contact_name:'Дмитро',contact_phone:'0671234567',city:'Київ',address:'Відділення №1',terms_accepted:true,delivery_method:'warehouse'}
  assert.deepEqual(checkoutErrors(form),{})
  assert.ok(checkoutErrors({...form,contact_surname:'а'.repeat(64),contact_name:'б'.repeat(128),contact_patronymic:'в'.repeat(64)}).contact_name)
  assert.ok(checkoutErrors({...form,address:' ',terms_accepted:false}).address)
  assert.ok(checkoutErrors({...form,terms_accepted:false}).terms_accepted)
})
test('acquisition uses bounded UTM fields and excludes unrelated URL parameters',()=>{
  assert.equal(campaignFromSearch('?q=парфум'),null)
  const data=campaignFromSearch('?utm_source=google&utm_medium=cpc&utm_campaign=Autumn&email=private@example.test&utm_term='+ 'a'.repeat(200))
  assert.equal(data.source,'google');assert.equal(data.campaign,'Autumn');assert.equal(data.term.length,160)
  assert.equal(data.email,undefined)
})

test('one anonymous visit per tab is sent once and survives a failed POST (A07)',async()=>{
  const {visitId,recordVisit}=await import('../src/checkout.js')
  const memory=new Map()
  const storage={getItem:k=>memory.has(k)?memory.get(k):null,setItem:(k,v)=>memory.set(k,String(v))}
  const id=visitId(storage,()=>'0123456789abcdef-0123')
  assert.equal(id,'0123456789abcdef0123')
  assert.equal(visitId(storage,()=>'other-value-should-not-replace'),id,'the same tab keeps its visit')
  const calls=[]
  const failing=async(url,options)=>{calls.push([url,JSON.parse(options.body)]);return {ok:false}}
  assert.equal(await recordVisit(failing,storage),false)
  const ok=async(url,options)=>{calls.push([url,JSON.parse(options.body)]);return {ok:true}}
  assert.equal(await recordVisit(ok,storage),true)
  assert.equal(await recordVisit(ok,storage),true)
  assert.equal(calls.length,2,'after success no further POST in this tab')
  assert.equal(calls[1][0],'/api/web/analytics/visit')
  assert.deepEqual(Object.keys(calls[1][1]).sort(),['attribution','session_id'])
  assert.equal(calls[1][1].session_id,id)
})
test('blocked storage disables visits instead of breaking the page',async()=>{
  const {visitId,recordVisit}=await import('../src/checkout.js')
  const broken={getItem(){throw new Error('denied')},setItem(){throw new Error('denied')}}
  assert.equal(visitId(broken),'')
  assert.equal(await recordVisit(async()=>{throw new Error('must not be called')},broken),false)
})
