import test from 'node:test'
import assert from 'node:assert/strict'
import { cartStartParam, sanitizeCart, telegramCheckoutUrl } from '../src/catalog.js'
const products=[
 {id:1,brand:'CREED',name:'Aventus 2 мл',gender:'male',volume_ml:2,price:180,stock:5,is_featured:true},
 {id:2,brand:'CREED',name:'Aventus 5 мл',gender:'male',volume_ml:5,price:375,stock:3},
 {id:3,brand:'NASOMATTO',name:'Black Afgano',gender:'male',volume_ml:null,price:300,stock:0},
]
test('site cart links include SKUs+absolute quantities only',()=>{
 const cart={1:2,2:1};assert.equal(cartStartParam(cart,products),'cart_1x2-2x1');assert.equal(telegramCheckoutUrl('https://t.me/elfarshop_bot/elfar',cart,products),'https://t.me/elfarshop_bot/elfar?startapp=cart_1x2-2x1')
})
test('invalid cart quantities and untrusted hosts cannot create links',()=>{
 assert.equal(cartStartParam({1:100},products),'');assert.equal(telegramCheckoutUrl('https://evil.example/tg', {1:1},products),'')
})

test('stale SKUs and malformed persisted cart entries are removed safely',()=>{
 assert.deepEqual(sanitizeCart({'1':100,'2':2,'3':1,'999':4,'garbage':9},products),{'1':5,'2':2})
 assert.deepEqual(sanitizeCart(null,products),{})
 assert.deepEqual(sanitizeCart(['bad'],products),{})
})

test('a Telegram handoff never silently drops cart lines',()=>{
 const items=Array.from({length:21},(_,i)=>({id:i+1,stock:1}))
 const cart=Object.fromEntries(items.map(p=>[p.id,1]))
 assert.equal(cartStartParam(cart,items),'')
})
test('website cart is bounded to the server limit of 30 lines',()=>{
 const items=Array.from({length:35},(_,i)=>({id:i+1,stock:1}))
 const cart=Object.fromEntries(items.map(p=>[p.id,1]))
 assert.equal(Object.keys(sanitizeCart(cart,items)).length,30)
})

test('handoff rejects missing, out-of-stock and excessive lines as a whole',()=>{
 for(const cart of [{1:1,999:1},{1:1,3:1},{1:6}])assert.equal(cartStartParam(cart,products),'')
})
