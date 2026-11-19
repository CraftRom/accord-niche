import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync,readdirSync} from 'node:fs'
import {JSDOM} from 'jsdom'

const assets=new URL('../dist/assets/',import.meta.url)
const bundle=readFileSync(new URL(readdirSync(assets).find(name=>/^index-.*\.js$/.test(name)),assets),'utf8')
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})
const order=id=>({id,total:'100',status_label:'Нове',items:[],created_at:'2026-11-16T09:00:00Z'})
const button=(doc,text)=>[...doc.querySelectorAll('button')].find(node=>node.textContent.trim()===text)
async function waitFor(check){const until=Date.now()+4000;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,15))}assert.ok(check(),'Profile did not become ready')}
function mount({fail=false}={}){
 const dom=new JSDOM('<html><body><div id="root"></div></body></html>',{url:'https://accordniche.pp.ua/profile',runScripts:'outside-only',pretendToBeVisual:true})
 const window=dom.window,calls=[]
 let listReads=0,resolveMore
 window.scrollTo=()=>{};window.confirm=()=>true
 window.fetch=async(input,options={})=>{
  const url=new URL(input,window.location.href);calls.push(url)
  if(url.pathname==='/api/web/session')return response({account:{has_session:true,signed_in:false,account_key:'guest-one'},csrf:'a'.repeat(48)})
  if(url.pathname==='/api/public/site-config')return response({})
  if(url.pathname==='/api/web/profile')return response({orders_count:2,bonus_balance:0})
  if(url.pathname==='/api/web/orders'){
   if(fail)return response({detail:'Не вдалося завантажити історію'},503)
   if(url.searchParams.get('offset')!=='0')return new Promise(resolve=>{resolveMore=resolve})
   listReads++;return response({items:[order(listReads===1?11:33)],has_more:listReads===1})
  }
  return response({},404)
 }
 window.eval(bundle)
 return {window,document:window.document,calls,releaseMore:()=>resolveMore(response({items:[order(22)],has_more:true})),close:()=>window.close()}
}

test('late history pagination cannot append an old page after refresh',async()=>{
 const app=mount()
 try{
  await waitFor(()=>button(app.document,'ПОКАЗАТИ БІЛЬШЕ ЗАМОВЛЕНЬ'))
  button(app.document,'ПОКАЗАТИ БІЛЬШЕ ЗАМОВЛЕНЬ').click()
  await waitFor(()=>app.calls.some(url=>url.pathname==='/api/web/orders'&&url.searchParams.get('offset')==='1'))
  button(app.document,'Оновити').click()
  await waitFor(()=>app.document.querySelector('.order-record-head')?.textContent.includes('33'))
  app.releaseMore()
  await new Promise(resolve=>setTimeout(resolve,35))
  assert.equal(app.document.querySelectorAll('.order-record').length,1)
  assert.doesNotMatch(app.document.querySelector('.orders-section').textContent,/№22/)
  assert.equal(button(app.document,'ПОКАЗАТИ БІЛЬШЕ ЗАМОВЛЕНЬ'),undefined)
 }finally{app.close()}
})

test('failed history loading does not claim that purchase history is empty',async()=>{
 const app=mount({fail:true})
 try{
  await waitFor(()=>app.document.querySelector('.shop-error'))
  assert.doesNotMatch(app.document.querySelector('.orders-section').textContent,/Історія покупок поки порожня/)
  assert.equal(button(app.document,'Оновити').disabled,false)
 }finally{app.close()}
})

function mountSignedIn({sms=true,telegram=true}={}){
 const dom=new JSDOM('<html><body><div id="root"></div></body></html>',{url:'https://accordniche.pp.ua/profile',runScripts:'outside-only',pretendToBeVisual:true})
 const window=dom.window,posts=[],opened=[]
 const state={confirmed:false}
 window.scrollTo=()=>{};window.open=(url)=>{opened.push(url);return null}
 window.fetch=async(input,options={})=>{
  const url=new URL(input,window.location.href)
  if(options.method==='POST')posts.push(url.pathname)
  if(url.pathname==='/api/web/session')return response({csrf:'a'.repeat(48),phone_sms_enabled:sms,phone_telegram_enabled:telegram,phone_verification_enabled:sms||telegram,
   account:{has_session:true,signed_in:true,account_key:'acc',name:'Олена',email:'o@example.com',phone:state.confirmed?'+380671234567':null,phone_verified:state.confirmed,telegram_linked:state.confirmed}})
  if(url.pathname==='/api/web/profile/phone/telegram')return response({url:'https://t.me/accord_shop_bot?start=vp_'+'x'.repeat(32),expires_in_seconds:600})
  if(url.pathname==='/api/public/site-config')return response({})
  if(url.pathname==='/api/web/profile')return response({orders_count:0,bonus_balance:0})
  if(url.pathname==='/api/web/orders')return response({items:[],has_more:false})
  return response({},404)
 }
 window.eval(bundle)
 return {window,document:window.document,posts,opened,state,close:()=>window.close()}
}
async function waitLong(check,ms=6000){const until=Date.now()+ms;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,25))}assert.ok(check(),'condition not reached')}

test('phone is confirmed through the Telegram bot without SMS; the card updates by itself',async()=>{
 const app=mountSignedIn()
 try{
  await waitLong(()=>button(app.document,'ПІДТВЕРДИТИ ЧЕРЕЗ TELEGRAM'))
  assert.ok(button(app.document,'НАДІСЛАТИ КОД'),'SMS stays available as the second way')
  button(app.document,'ПІДТВЕРДИТИ ЧЕРЕЗ TELEGRAM').click()
  await waitLong(()=>app.opened.length===1)
  assert.match(app.opened[0],/^https:\/\/t\.me\/accord_shop_bot\?start=vp_/)
  assert.deepEqual(app.posts.filter(path=>path.includes('/profile/')),['/api/web/profile/phone/telegram'])
  const link=[...app.document.querySelectorAll('a')].find(a=>a.textContent==='відкрийте бота')
  assert.equal(link.getAttribute('href'),app.opened[0])
  app.state.confirmed=true  // the bot received the user's own contact
  await waitLong(()=>/Номер \+380671234567 підтверджено/.test(app.document.body.textContent))
  assert.equal(button(app.document,'ПІДТВЕРДИТИ ЧЕРЕЗ TELEGRAM'),undefined)
 }finally{app.close()}
})

test('without an SMS gateway the profile offers only Telegram, never a dead SMS form',async()=>{
 const app=mountSignedIn({sms:false})
 try{
  await waitLong(()=>button(app.document,'ПІДТВЕРДИТИ ЧЕРЕЗ TELEGRAM'))
  assert.equal(button(app.document,'НАДІСЛАТИ КОД'),undefined)
 }finally{app.close()}
})
