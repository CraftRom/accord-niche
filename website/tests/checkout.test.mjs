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
