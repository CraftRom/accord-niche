import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync, readdirSync} from 'node:fs'
import {JSDOM} from 'jsdom'

const assets = new URL('../dist/assets/', import.meta.url)
const entry = readdirSync(assets).find(name => /^index-.*\.js$/.test(name))
const bundle = readFileSync(new URL(entry, assets), 'utf8')
const products = [
  {id:42,name:'Actual Aroma 2 мл',brand:'DB BRAND',gender:'unisex',volume_ml:2,price:'40',stock:4,photo_url:null,photo_endpoint:null,is_new:true,is_featured:false},
  {id:43,name:'Actual Aroma 5 мл',brand:'DB BRAND',gender:'unisex',volume_ml:5,price:'75',stock:2,photo_url:null,photo_endpoint:null,is_new:true,is_featured:false},
]
const aroma = {id:42,key:'db:actual',name:'Actual Aroma',brand:'DB BRAND',gender:'unisex',description:'Опис із каталогу',variants:products,categories:[],stock:6,min_price:'40',price_per_ml:'15',image:'',volumes:[2,5],is_new:true,is_featured:false,is_set:false,bestseller_rank:1}
const other = {...aroma,id:60,key:'other:real',name:'Other Real Aroma',brand:'OTHER',variants:[{...products[0],id:60,brand:'OTHER'}],bestseller_rank:null}
const home = {hits:[aroma],recommended:[],new_arrivals:[],selection:[aroma],total:2,available:2,window_days:90}
const response = (data,status=200) => new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})
async function waitFor(check) {
  const until = Date.now()+4000
  while (Date.now()<until) {if (check()) return; await new Promise(resolve => setTimeout(resolve,15))}
  assert.ok(check(), 'DOM state did not become ready')
}
function mount({empty=false, saved={}, failCart=false, failHome=false, failDetailAfterLoad=false, path='/'}={}) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',{url:'https://accordniche.pp.ua'+path,runScripts:'outside-only',pretendToBeVisual:true})
  const window=dom.window
  let homeFailed=false,detailReads=0
  window.scrollTo=()=>{}
  window.localStorage.setItem('accord:niche:cart',JSON.stringify(saved))
  window.fetch=async (input) => {
    const url=new URL(input,window.location.href)
    if(url.pathname==='/api/web/session') return response({account:{signed_in:false,has_session:false},csrf:'a'.repeat(48)})
    if(url.pathname==='/api/public/site-config') return response({phone:'+380501234567',seller_name:'Продавець із БД'})
    if(url.pathname==='/api/public/storefront') {
      if(failHome&&!homeFailed){homeFailed=true;return response({},503)}
      return response(empty?{...home,hits:[],selection:[],total:0,available:0}:home)
    }
    if(['/api/public/aromas/42','/api/public/aromas/43'].includes(url.pathname)){detailReads++;return failDetailAfterLoad&&detailReads>1?response({},404):response({item:aroma,related:[other]})}
    if(url.pathname==='/api/public/products') return failCart?response({},503):response(products.filter(p=>url.searchParams.get('ids').split(',').includes(String(p.id))))
    if(url.pathname==='/api/public/aromas') {
      const items=empty?[]:[aroma,other].filter(g=>!url.searchParams.get('brand')||g.brand===url.searchParams.get('brand'))
      return response({items,total:items.length,limit:24,offset:0,brands:empty?[]:['DB BRAND','OTHER'],categories:[],updated_at:new Date().toISOString()})
    }
    return response({},404)
  }
  window.eval(bundle)
  return {window, document:window.document, close:()=>window.close()}
}
const button = (document,text) => [...document.querySelectorAll('button')].find(button=>button.textContent.trim()===text)

test('homepage renders API products and real prices, without editorial SKU stand-ins',async()=>{
 const app=mount()
 try {
  await waitFor(()=>app.document.querySelector('.product-card h3'))
  assert.equal(app.document.querySelector('.product-card h3').textContent,'Actual Aroma')
  assert.match(app.document.querySelector('.product-meta strong').textContent,/40 грн/)
  assert.match(app.document.body.textContent,/підтвердженими продажами за 90 днів/)
  assert.doesNotMatch(app.document.body.textContent,/\[ЦІНА\]|\[ФОТО|Aventus|Black Afgano/)
  assert.match(app.document.querySelector('.footer').textContent,/Продавець із БД/)
 } finally {app.close()}
})
test('an empty API catalog creates no fake cards, brands or bestseller headings',async()=>{
 const app=mount({empty:true})
 try {
  await waitFor(()=>app.document.querySelector('.store-state'))
  assert.equal(app.document.querySelectorAll('.product-card').length,0)
  assert.doesNotMatch(app.document.body.textContent,/Хіти розливу|\[ЦІНА\]|Aventus/)
 } finally {app.close()}
})
test('API failure is explicit and retry loads actual products',async()=>{
 const app=mount({failHome:true})
 try {
  await waitFor(()=>button(app.document,'Спробувати ще раз'))
  button(app.document,'Спробувати ще раз').click()
  await waitFor(()=>app.document.querySelector('.product-card h3'))
  assert.equal(app.document.querySelector('.product-card h3').textContent,'Actual Aroma')
 } finally {app.close()}
})
test('detail selects a real volume, hydrates the cart and enforces current stock',async()=>{
 const app=mount()
 try {
  await waitFor(()=>app.document.querySelector('.product-link'))
  app.document.querySelector('.product-link').click()
  await waitFor(()=>button(app.document,'5 мл'))
  button(app.document,'5 мл').click()
  await waitFor(()=>button(app.document,'5 мл').getAttribute('aria-pressed')==='true')
  button(app.document,'ДОДАТИ В КОШИК').click()
  await waitFor(()=>app.document.querySelector('.basket-line'))
  assert.match(app.document.querySelector('.basket-info strong').textContent,/75 грн/)
  app.document.querySelector('[aria-label="Збільшити кількість"]').click()
  await waitFor(()=>app.document.querySelector('[aria-label="Збільшити кількість"]').disabled)
  assert.deepEqual(JSON.parse(app.window.localStorage.getItem('accord:niche:cart')),{'43':2})
 } finally {app.close()}
})
test('a failed stock refresh preserves a saved cart',async()=>{
 const app=mount({saved:{42:1},failCart:true})
 try {
  await waitFor(()=>app.document.querySelector('.product-card'))
  app.document.querySelector('.cart-button').click()
  await waitFor(()=>app.document.querySelector('.basket [role="alert"]'))
  assert.deepEqual(JSON.parse(app.window.localStorage.getItem('accord:niche:cart')),{'42':1})
 } finally {app.close()}
})
test('catalog filters request the server and retain a shareable URL',async()=>{
 const app=mount({path:'/catalog'})
 try {
  await waitFor(()=>app.document.querySelectorAll('.product-card').length===2)
  const select=[...app.document.querySelectorAll('.catalog-filters select')][0]
  select.value='OTHER'
  select.dispatchEvent(new app.window.Event('change',{bubbles:true}))
  await waitFor(()=>app.document.querySelectorAll('.product-card').length===1)
  assert.equal(app.document.querySelector('.product-card h3').textContent,'Other Real Aroma')
  assert.equal(app.window.location.search,'?brand=OTHER')
 } finally {app.close()}
})


test('a removed product does not remain buyable after a definitive not-found refresh',async()=>{
 const app=mount({path:'/aroma/42',failDetailAfterLoad:true})
 try{
  await waitFor(()=>button(app.document,'ДОДАТИ В КОШИК'))
  app.document.dispatchEvent(new app.window.Event('visibilitychange'))
  await waitFor(()=>app.document.querySelector('[role="alert"] h2')?.textContent==='Товар недоступний')
  assert.equal(button(app.document,'ДОДАТИ В КОШИК'),undefined)
  assert.equal(app.document.querySelector('.detail-buy'),null)
 }finally{app.close()}
})
