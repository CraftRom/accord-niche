import test from 'node:test'
import assert from 'node:assert/strict'
import { groupProducts, unitPrice, referenceCards, cartStartParam, sanitizeCart, telegramCheckoutUrl } from '../src/catalog.js'
const products=[
 {id:1,brand:'CREED',name:'Aventus 2 мл',gender:'male',volume_ml:2,price:180,stock:5,is_featured:true},
 {id:2,brand:'CREED',name:'Aventus 5 мл',gender:'male',volume_ml:5,price:375,stock:3},
 {id:3,brand:'NASOMATTO',name:'Black Afgano',gender:'male',volume_ml:null,price:300,stock:0},
]
test('two sellable SKU variants group under one aroma, cheapest per ml',()=>{
 const groups=groupProducts(products); assert.equal(groups.length,2); assert.equal(groups[0].variants.length,2); assert.equal(groups[0].pricePerMl,75)
})
test('no false unit price if volume is missing',()=>assert.equal(unitPrice(products[2]),null))
test('reference order and placeholders without fabricated price',()=>{
 const cards=referenceCards(groupProducts(products));assert.equal(cards.length,8);assert.equal(cards[0].name,'Aventus');assert.equal(cards[1].preview,true)
})
test('site cart links include SKUs+absolute quantities only',()=>{
 const cart={1:2,2:1,3:3};assert.equal(cartStartParam(cart,products),'cart_1x2-2x1');assert.equal(telegramCheckoutUrl('https://t.me/elfarshop_bot/elfar',cart,products),'https://t.me/elfarshop_bot/elfar?startapp=cart_1x2-2x1')
})
test('invalid cart quantities and untrusted hosts cannot create links',()=>{
 assert.equal(cartStartParam({1:100},products),'');assert.equal(telegramCheckoutUrl('https://evil.example/tg', {1:1},products),'')
})

test('stale SKUs and malformed persisted cart entries are removed safely',()=>{
 assert.deepEqual(sanitizeCart({'1':100,'2':2,'3':1,'999':4,'garbage':9},products),{'1':5,'2':2})
 assert.deepEqual(sanitizeCart(null,products),{})
 assert.deepEqual(sanitizeCart(['bad'],products),{})
})
