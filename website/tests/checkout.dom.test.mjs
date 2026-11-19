import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync,readdirSync} from 'node:fs'
import {JSDOM} from 'jsdom'

const assets=new URL('../dist/assets/',import.meta.url)
const bundle=readFileSync(new URL(readdirSync(assets).find(name=>/^index-.*\.js$/.test(name)),assets),'utf8')
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})
const product={id:42,name:'Реальний аромат 5 мл',brand:'Бренд',volume_ml:5,price:'100',stock:5}
const button=(document,text)=>[...document.querySelectorAll('button')].find(node=>node.textContent.trim()===text)
async function waitFor(check){const until=Date.now()+5000;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,15))}assert.ok(check(),'Checkout DOM did not become ready')}
function input(window,node,value){Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new window.Event('input',{bubbles:true}))}
function mount({mode='normal',path='/checkout',pending=null,defaults=null,cityRequests=null,site={}}={}){
  const dom=new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',{url:'https://accordniche.pp.ua'+path,runScripts:'outside-only',pretendToBeVisual:true})
  const window=dom.window,calls=[]
  let price=100,cartFailure=false,accepted=pending?99:null,posts=0
  window.scrollTo=()=>{};window.confirm=()=>true
  window.localStorage.setItem('accord:niche:cart',JSON.stringify({42:1}))
  if(pending)window.sessionStorage.setItem('accord:checkout:attempt',pending)
  window.fetch=async(input,options={})=>{
    const url=new URL(input,window.location.href),method=options.method || 'GET'
    calls.push({url,method,options})
    if(url.pathname==='/api/web/session')return response({account:{has_session:true,signed_in:false,account_key:'guest-one'},csrf:'a'.repeat(48)})
    if(url.pathname==='/api/public/site-config')return response(site)
    if(url.pathname==='/api/public/products')return cartFailure?response({},503):response([{...product,price:String(price)}])
    if(url.pathname==='/api/web/delivery/config')return response({courier_enabled:true,novaposhta_enabled:Boolean(cityRequests)})
    if(url.pathname==='/api/web/checkout/defaults')return defaults?defaults:response({})
    if(url.pathname==='/api/web/delivery/cities')return cityRequests(url.searchParams.get('q'))
    if(url.pathname==='/api/web/delivery/warehouses')return response({items:[{ref:'branch-one',label:'Відділення №1',number:'1'}]})
    if(url.pathname==='/api/web/checkout/quote'){
      const {items}=JSON.parse(options.body),qty=items[0].qty
      return response({subtotal:String(price*qty),discount:'0',bonus_used:'0',bonus_available:'0',total:String(price*qty),quote_token:(price===100?'a':'b').repeat(64),items:[{product_id:42,qty,unit_price:String(price),line_total:String(price*qty)}]})
    }
    if(url.pathname==='/api/web/checkout/status')return response(accepted?{found:true,order_id:accepted,total:'100',payment_method:'cod'}:{found:false})
    if(url.pathname==='/api/web/checkout' && method==='POST'){
      posts++
      if(mode==='changed' && posts===1){price=150;return response({detail:'Сума змінилася. Перевірте оновлений підсумок.',code:'checkout_changed'},409)}
      accepted=99
      if(mode==='lost' && posts===1)throw new TypeError('З’єднання перервано')
      return response({order_id:accepted,total:String(price),payment_method:'cod',replayed:posts>1})
    }
    return response({},404)
  }
  window.eval(bundle)
  return {window,document:window.document,calls,failCart:()=>{cartFailure=true;window.document.dispatchEvent(new window.Event('visibilitychange'))},close:()=>window.close()}
}
function fill(app){
  for(const [name,value] of Object.entries({contact_surname:'Покупець',contact_name:'Дмитро',contact_phone:'0671234567',city:'Київ',address:'Відділення №1'}))input(app.window,app.document.getElementById('accord-'+name),value)
  app.document.querySelector('[name="terms_accepted"]').click()
}
function submit(app){app.document.querySelector('#accord-checkout').dispatchEvent(new app.window.Event('submit',{bubbles:true,cancelable:true}))}

test('checkout exposes field errors and never submits incomplete contact data',async()=>{
  const app=mount()
  try{
    await waitFor(()=>button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'))
    submit(app)
    await waitFor(()=>app.document.querySelectorAll('[aria-invalid=true]').length===6)
    assert.equal(app.calls.filter(call=>call.url.pathname==='/api/web/checkout').length,0)
    assert.equal(app.document.getElementById('accord-contact_phone').getAttribute('aria-describedby'),'accord-contact_phone-error')
    await waitFor(()=>app.document.activeElement.id==='accord-contact_surname')
  }finally{app.close()}
})

test('confirmation uses the displayed quote and does not silently calculate a new one',async()=>{
  const app=mount()
  try{
    await waitFor(()=>button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'))
    fill(app)
    const quoteCount=app.calls.filter(call=>call.url.pathname.endsWith('/checkout/quote')).length
    submit(app)
    await waitFor(()=>app.window.location.pathname==='/order/success')
    assert.match(app.document.body.textContent,/Замовлення №99 прийнято/)
    assert.equal(app.calls.filter(call=>call.url.pathname.endsWith('/checkout/quote')).length,quoteCount)
    const sent=app.calls.find(call=>call.url.pathname==='/api/web/checkout')
    const data=JSON.parse(sent.options.body)
    assert.equal(data.quote_token,'a'.repeat(64));assert.equal(data.contact_phone,'+380671234567')
    assert.equal(sent.options.headers['X-CSRF-Token'],'a'.repeat(48))
    assert.equal(app.window.sessionStorage.getItem('accord:checkout:attempt'),null)
  }finally{app.close()}
})

test('changed server prices need another explicit confirmation',async()=>{
  const app=mount({mode:'changed'})
  try{
    await waitFor(()=>button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'))
    fill(app);submit(app)
    await waitFor(()=>app.document.querySelector('.summary-total.final').textContent.includes('150') && button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'))
    assert.equal(app.calls.filter(call=>call.url.pathname==='/api/web/checkout').length,1)
    assert.equal(app.document.getElementById('accord-contact_name').value,'Дмитро')
    submit(app)
    await waitFor(()=>app.window.location.pathname==='/order/success')
    const posted=app.calls.filter(call=>call.url.pathname==='/api/web/checkout').map(call=>JSON.parse(call.options.body))
    assert.notEqual(posted[0].quote_token,posted[1].quote_token)
    assert.notEqual(posted[0].checkout_key,posted[1].checkout_key)
    // A07: the order carries the same anonymous visit id the tab recorded.
    const visit=app.calls.find(call=>call.url.pathname==='/api/web/analytics/visit')
    assert.ok(visit,'the tab records its visit')
    const visitId=JSON.parse(visit.options.body).session_id
    assert.match(visitId,/^[A-Za-z0-9_-]{16,64}$/)
    assert.ok(posted.every(body=>body.attribution.session_id===visitId))
  }finally{app.close()}
})

test('an uncertain result retains the exact request and retries without making a second intent',async()=>{
  const app=mount({mode:'lost'})
  try{
    await waitFor(()=>button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'))
    fill(app);submit(app)
    await waitFor(()=>button(app.document,'ПОВТОРИТИ ПІДТВЕРДЖЕННЯ') && !button(app.document,'ПОВТОРИТИ ПІДТВЕРДЖЕННЯ').disabled)
    assert.equal(app.document.querySelector('.checkout-fields').disabled,true)
    assert.ok(app.window.sessionStorage.getItem('accord:checkout:attempt'))
    submit(app)
    await waitFor(()=>app.window.location.pathname==='/order/success')
    const posted=app.calls.filter(call=>call.url.pathname==='/api/web/checkout')
    assert.equal(posted.length,2);assert.equal(posted[0].options.body,posted[1].options.body)
  }finally{app.close()}
})

test('a reloaded uncertain checkout checks the saved key before any new purchase',async()=>{
  const app=mount({mode:'lost'})
  let pending
  try{
    await waitFor(()=>button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'));fill(app);submit(app)
    await waitFor(()=>button(app.document,'ПОВТОРИТИ ПІДТВЕРДЖЕННЯ'))
    pending=app.window.sessionStorage.getItem('accord:checkout:attempt')
  }finally{app.close()}
  const reloaded=mount({pending})
  try{
    await waitFor(()=>reloaded.window.location.pathname==='/order/success')
    assert.equal(reloaded.calls.filter(call=>call.url.pathname==='/api/web/checkout').length,0)
    assert.equal(reloaded.window.sessionStorage.getItem('accord:checkout:attempt'),null)
  }finally{reloaded.close()}
})

test('a cart refresh failure keeps entered contacts visible',async()=>{
  const app=mount()
  try{
    await waitFor(()=>button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'))
    input(app.window,app.document.getElementById('accord-contact_name'),'Мій незбережений ввід')
    app.failCart()
    await waitFor(()=>app.document.querySelector('.notice')?.textContent.includes('Не вдалося'))
    assert.equal(app.document.getElementById('accord-contact_name').value,'Мій незбережений ввід')
    assert.equal(button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ').disabled,true)
  }finally{app.close()}
})

test('late defaults do not replace typed city or attach another city reference',async()=>{
  let resolveDefaults
  const defaults=new Promise(resolve=>{resolveDefaults=resolve})
  const app=mount({defaults,cityRequests:()=>response({items:[]})})
  try{
    await waitFor(()=>app.document.getElementById('accord-city'))
    input(app.window,app.document.getElementById('accord-city'),'Львів')
    resolveDefaults(response({city:'Київ',delivery_city_ref:'wrong-old-city',delivery_warehouse_ref:'wrong-old-branch',address:'Стара адреса'}))
    await new Promise(resolve=>setTimeout(resolve,450))
    assert.equal(app.document.getElementById('accord-city').value,'Львів')
    assert.ok(!app.calls.some(call=>call.url.pathname.endsWith('/warehouses')&&call.url.searchParams.get('city_ref')==='wrong-old-city'))
  }finally{app.close()}
})

test('stale city searches cannot overwrite a newer selection',async()=>{
  let resolveOld
  const old=new Promise(resolve=>{resolveOld=resolve})
  const app=mount({cityRequests:q=>q==='Ки'?old:response({items:[{ref:'lviv',label:'Львів',settlement_ref:'lviv-settlement'}]})})
  try{
    await waitFor(()=>app.document.getElementById('accord-city'))
    input(app.window,app.document.getElementById('accord-city'),'Ки')
    await waitFor(()=>app.calls.some(call=>call.url.pathname.endsWith('/cities')&&call.url.searchParams.get('q')==='Ки'))
    input(app.window,app.document.getElementById('accord-city'),'Ль')
    await waitFor(()=>button(app.document,'Львів'))
    button(app.document,'Львів').click()
    resolveOld(response({items:[{ref:'kyiv',label:'Київ'}]}))
    await new Promise(resolve=>setTimeout(resolve,50))
    assert.equal(app.document.getElementById('accord-city').value,'Львів')
    assert.equal(button(app.document,'Київ'),undefined)
  }finally{app.close()}
})

test('courier switch removes warehouse address and directory selection',async()=>{
  const app=mount({cityRequests:()=>response({items:[{ref:'kyiv',label:'Київ'}]})})
  try{
    await waitFor(()=>app.document.getElementById('accord-city'))
    input(app.window,app.document.getElementById('accord-city'),'Ки')
    await waitFor(()=>button(app.document,'Київ'));button(app.document,'Київ').click()
    await waitFor(()=>button(app.document,'Відділення №1'));button(app.document,'Відділення №1').click()
    const radio=[...app.document.querySelectorAll('[name="delivery-method"]')][1];radio.click()
    await waitFor(()=>app.document.getElementById('accord-address').value==='')
    assert.equal(app.document.querySelector('[aria-label="Знайдені відділення"]'),null)
    for(const [name,value] of Object.entries({contact_surname:'Покупець',contact_name:'Дмитро',contact_phone:'0671234567',address:'Вулиця, будинок 12'}))input(app.window,app.document.getElementById('accord-'+name),value)
    app.document.querySelector('[name="terms_accepted"]').click()
    await waitFor(()=>button(app.document,'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'));submit(app)
    await waitFor(()=>app.window.location.pathname==='/order/success')
    const sent=JSON.parse(app.calls.find(call=>call.url.pathname==='/api/web/checkout').options.body)
    assert.equal(sent.delivery_method,'courier');assert.equal(sent.delivery_warehouse_ref,null);assert.equal(sent.delivery_city_ref,'kyiv')
  }finally{app.close()}
})

test('opening success URL directly never claims an order was created',async()=>{
  const app=mount({path:'/order/success'})
  try{
    await waitFor(()=>app.document.querySelector('h1'))
    assert.equal(app.document.querySelector('h1').textContent,'Перевірка замовлення')
    assert.doesNotMatch(app.document.body.textContent,/Замовлення №.*прийнято|Дякуємо за замовлення/)
  }finally{app.close()}
})

test('Nova Poshta suggestions are a keyboard combobox; Enter picks without submitting (W-09)',async()=>{
  const app=mount({cityRequests:()=>response({items:[{ref:'kyiv',label:'Київ'},{ref:'lviv',label:'Львів'}]})})
  try{
    await waitFor(()=>app.document.getElementById('accord-city'))
    const city=app.document.getElementById('accord-city')
    input(app.window,city,'Ки')
    await waitFor(()=>city.getAttribute('aria-expanded')==='true')
    assert.equal(city.getAttribute('role'),'combobox')
    const list=app.document.getElementById(city.getAttribute('aria-controls'))
    assert.equal(list.getAttribute('role'),'listbox')
    assert.deepEqual([...list.querySelectorAll('[role="option"]')].map(o=>o.textContent),['Київ','Львів'])
    const key=name=>{const event=new app.window.KeyboardEvent('keydown',{key:name,bubbles:true,cancelable:true});city.dispatchEvent(event);return event}
    key('ArrowDown');key('ArrowDown')
    await waitFor(()=>city.getAttribute('aria-activedescendant')===list.id+'-1')
    assert.equal(app.document.getElementById(city.getAttribute('aria-activedescendant')).getAttribute('aria-selected'),'true')
    const enter=key('Enter')
    assert.equal(enter.defaultPrevented,true,'Enter picks the suggestion instead of submitting the order')
    await waitFor(()=>city.value==='Львів')
    assert.equal(city.getAttribute('aria-expanded'),'false')
    assert.equal(app.calls.filter(call=>call.url.pathname==='/api/web/checkout').length,0)
    input(app.window,city,'Ки')
    await waitFor(()=>city.getAttribute('aria-expanded')==='true')
    key('Escape')
    await waitFor(()=>city.getAttribute('aria-expanded')==='false')
    assert.equal(city.value,'Ки','Escape closes the list and keeps what was typed')
  }finally{app.close()}
})

test('the consent shows the delivery and return terms in place; legal links only when configured (W-10)',async()=>{
  const app=mount()
  try{
    await waitFor(()=>app.document.querySelector('.consent-docs'))
    const docs=app.document.querySelector('.consent-docs')
    assert.deepEqual([...docs.querySelectorAll('summary')].map(s=>s.textContent),['Доставка й оплата','Повернення та скасування'])
    const links=[...docs.querySelectorAll('.consent-links a')]
    assert.deepEqual(links.map(a=>a.getAttribute('href')),['/terms','/privacy'],'the consent links the shop\'s own documents')
  }finally{app.close()}
})

test('terms and privacy open in a new tab so the filled form is kept (W-10)',async()=>{
  const app=mount()
  try{
    await waitFor(()=>app.document.querySelector('.consent-links'))
    const links=[...app.document.querySelectorAll('.consent-links a')]
    assert.deepEqual(links.map(a=>[a.textContent,a.getAttribute('href'),a.target]),[['Публічна оферта','/terms','_blank'],['Політика конфіденційності','/privacy','_blank']])
    assert.ok(links.every(a=>a.rel.includes('noopener')))
  }finally{app.close()}
})

test('the order summary folds into one line with a labelled toggle (W-08)',async()=>{
  const app=mount()
  try{
    // The toggle renders before the cart products load; wait for the real summary.
    await waitFor(()=>/1 шт\. · 100 грн/.test(app.document.querySelector('.summary-toggle')?.textContent || ''))
    const toggle=app.document.querySelector('.summary-toggle')
    assert.equal(toggle.getAttribute('aria-expanded'),'false')
    assert.equal(toggle.getAttribute('aria-controls'),'checkout-summary-lines')
    assert.match(toggle.textContent,/1 шт\. · 100 грн/)
    toggle.click()
    await waitFor(()=>toggle.getAttribute('aria-expanded')==='true')
    assert.ok(app.document.getElementById('checkout-summary-lines').classList.contains('is-open'))
    assert.match(toggle.textContent,/Сховати товари/)
  }finally{app.close()}
})
