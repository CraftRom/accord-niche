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
