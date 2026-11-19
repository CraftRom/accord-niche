import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync,readdirSync} from 'node:fs'
import {JSDOM} from 'jsdom'
const assets=new URL('../dist/assets/',import.meta.url)
const bundle=readFileSync(new URL(readdirSync(assets).find(name=>/^index-.*\.js$/.test(name)),assets),'utf8')
const response=data=>new Response(JSON.stringify(data),{status:200,headers:{'content-type':'application/json'}})
async function waitFor(check){const until=Date.now()+4000;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,15))}assert.ok(check(),'Interface state did not become ready')}
function mount(){
 const dom=new JSDOM('<!doctype html><body><div id="root"></div></body>',{url:'https://accordniche.pp.ua/',runScripts:'outside-only',pretendToBeVisual:true})
 const window=dom.window;window.scrollTo=()=>{}
 window.fetch=async(input)=>{
  const url=new URL(input,window.location.href)
  if(url.pathname==='/api/web/session')return response({account:{has_session:false,signed_in:false},csrf:'a'.repeat(48)})
  if(url.pathname==='/api/public/site-config')return response({})
  if(url.pathname==='/api/public/storefront')return response({hits:[],recommended:[],new_arrivals:[],selection:[],total:0,available:0})
  if(url.pathname==='/api/public/aromas')return response({items:[],total:0,brands:[],volumes:[]})
  return response({})
 }
 window.eval(bundle)
 return {window,document:window.document,close:()=>window.close()}
}
const button=(document,label)=>[...document.querySelectorAll('button')].find(node=>node.textContent.trim()===label)
test('information window locks scrolling, contains focus and closes with Escape',async()=>{
 const app=mount()
 try{
  await waitFor(()=>button(app.document,'Доставка й оплата'))
  const trigger=button(app.document,'Доставка й оплата');trigger.focus();trigger.click()
  await waitFor(()=>app.document.querySelector('.info-modal') && app.document.body.style.overflow==='hidden')
  const dialog=app.document.querySelector('.info-modal')
  app.document.querySelector('[aria-label="Пошук"]').focus();assert.ok(dialog.contains(app.document.activeElement))
  app.document.dispatchEvent(new app.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))
  await waitFor(()=>!app.document.querySelector('.info-modal'))
  assert.equal(app.document.body.style.overflow,'');assert.equal(app.document.activeElement,trigger)
 }finally{app.close()}
})
test('search and mobile menu are exclusive and Escape restores their trigger',async()=>{
 const app=mount()
 try{
  await waitFor(()=>app.document.querySelector('[aria-label="Меню"]'))
  const menu=app.document.querySelector('[aria-label="Меню"]'),search=app.document.querySelector('[aria-label="Пошук"]')
  menu.click();await waitFor(()=>menu.getAttribute('aria-expanded')==='true')
  search.click();await waitFor(()=>app.document.querySelector('#store-search'))
  assert.equal(menu.getAttribute('aria-expanded'),'false')
  assert.equal(app.document.querySelector('#store-search input').maxLength,120)
  app.document.dispatchEvent(new app.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))
  await waitFor(()=>!app.document.querySelector('#store-search'))
  assert.equal(app.document.activeElement,search)
 }finally{app.close()}
})
test('opening the basket closes header overlays and restores focus on Escape',async()=>{
 const app=mount()
 try{
  await waitFor(()=>app.document.querySelector('[aria-label="Меню"]'))
  app.document.querySelector('[aria-label="Меню"]').click()
  const cart=app.document.querySelector('.cart-button');cart.focus();cart.click()
  await waitFor(()=>app.document.querySelector('.basket'))
  assert.equal(app.document.querySelector('[aria-label="Меню"]').getAttribute('aria-expanded'),'false')
  app.document.dispatchEvent(new app.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))
  await waitFor(()=>!app.document.querySelector('.basket'))
  assert.equal(app.document.activeElement,cart)
 }finally{app.close()}
})
