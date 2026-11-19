import test from 'node:test'
import assert from 'node:assert/strict'
import {recipientName,customerContact,customerName,customerSubtitle,paymentMeta,orderChannel,inventoryState,publicationState,navigationFor} from '../src/commerce.js'

test('recipient names support both normalized full names and older split fields',()=>{
 assert.equal(recipientName({contact_surname:'Покупець',contact_name:'Покупець Дмитро Іванович',contact_patronymic:'Іванович'}),'Покупець Дмитро Іванович')
 assert.equal(recipientName({contact_surname:'Покупець',contact_name:'Дмитро',contact_patronymic:'Іванович'}),'Покупець Дмитро Іванович')
 assert.equal(recipientName({contact_name:' Дмитро  Іванович ',contact_patronymic:'Іванович'}),'Дмитро Іванович')
})
test('website identities and missing payment methods never masquerade as Telegram or card payment',()=>{
 assert.equal(customerContact({tg_id:-999,username:'not_a_telegram_identity'}),'Покупець сайту')
 assert.equal(customerContact({tg_id:123,username:'realname'}),'@realname')
 assert.match(paymentMeta(null).title,/не вказано/)
})
test('customer names come from Telegram or the Google sign-in, never a placeholder id',()=>{
 assert.equal(customerName({tg_id:-4,first_name:null,display_name:'Олена Коваль'}),'Олена Коваль')
 assert.equal(customerName({tg_id:5,first_name:'Тарас',display_name:'Олена Коваль'}),'Тарас')
 assert.equal(customerName({tg_id:-4}),'Покупець сайту')
 assert.equal(customerSubtitle({id:4,tg_id:-4,email:'olena@example.com',phone:'+380671234567'}),'olena@example.com · +380671234567')
 assert.equal(customerSubtitle({id:4,tg_id:-4}),'Вебпокупець #4')
 assert.equal(customerSubtitle({id:5,tg_id:55,username:'taras'}),'@taras')
})
test('campaign source does not override the actual sales channel',()=>{
 assert.equal(orderChannel({attribution:{source:'google',channel:'accord_website'}}),'website')
 assert.equal(orderChannel({attribution:{source:'accord_website'}}),'website')
 assert.equal(orderChannel({attribution:{source:'telegram_bot'}}),'bot')
 assert.equal(orderChannel({attribution:{source:'google',session_id:'miniapp-session'}}),'miniapp')
 assert.equal(orderChannel({attribution:{source:'accord_website',channel:'telegram_miniapp'}}),'miniapp')
 assert.equal(orderChannel({attribution:{source:'unknown'}}),'unknown')
})
test('stock states match sellable website products instead of active flags alone',()=>{
 assert.match(inventoryState({is_active:true,price:0,stock:20}).label,/Без ціни/)
 assert.equal(inventoryState({is_active:true,price:100,stock:3}).tone,'warn')
 assert.equal(inventoryState({is_active:false,price:100,stock:3}).tone,'hidden')
 assert.equal(publicationState({name:'Аромат',is_active:true,price:0,stock:20}).visible,false)
 assert.deepEqual(publicationState({name:'Аромат',is_active:true,price:100,stock:0}),{visible:true,buyable:false,label:'На сайті, немає в наявності'})
})
test('grouped commerce navigation preserves role boundaries',()=>{
 const manager=navigationFor('operator').flatMap(group=>group.items).map(item=>item.to)
 assert.ok(manager.includes('/orders') && manager.includes('/catalog'))
 for(const path of ['/blog','/settings','/operators','/backups','/logs'])assert.ok(!manager.includes(path),path)
 assert.ok(navigationFor('shop_admin').flatMap(group=>group.items).some(item=>item.to==='/blog'))
 assert.ok(!navigationFor('shop_admin').flatMap(group=>group.items).some(item=>item.to==='/logs'))
 assert.deepEqual(navigationFor('unknown'),[])
})
