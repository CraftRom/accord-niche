import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync,readdirSync} from 'node:fs'
import {JSDOM} from 'jsdom'

const assets=new URL('../dist/assets/',import.meta.url)
const bundle=readFileSync(new URL(readdirSync(assets).find(name=>/^index-.*\.js$/.test(name)),assets),'utf8')
const article={id:5,slug:'real-article',title:'Стаття з бази',excerpt:'Опис із редактора',author_name:'Автор редакції',cover_url:'',published_at:'2026-11-01T10:00:00Z',updated_at:'2026-11-01T10:00:00Z',reading_minutes:2,comment_count:1,comments_enabled:true,
  body:'## Корисний заголовок\n\n**Справжній текст**\n\n<script>window.hacked=true</script>\n\n[Небезпечне](javascript:alert%281%29)\n\n![Небезпечне](data:image/svg+xml;base64,AAAA)\n\n[Каталог](https://accordniche.pp.ua/catalog)\n\n![Фото](/media/image-123.jpg)'}
const root={id:9,parent_id:null,author_name:'Покупець',is_staff:false,body:'<img src=x onerror=alert(1)>',created_at:'2026-11-02T11:00:00Z',updated_at:'2026-11-02T11:00:00Z',reply_count:0}
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})
async function waitFor(check){const until=Date.now()+4000;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,15))}assert.ok(check(),'Blog DOM did not become ready')}
const button=(document,text)=>[...document.querySelectorAll('button')].find(element=>element.textContent.trim()===text)
function input(window,element,value){Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set.call(element,value);element.dispatchEvent(new window.Event('input',{bubbles:true}))}
function mount({path='/blog/real-article',authenticated=false,closed=false,empty=false,alias=false,own=[],conflict=false}={}){
  const dom=new JSDOM('<!doctype html><html><head><title>ACCORD NICHE</title><meta name="description" content="Магазин"></head><body><div id="root"></div></body></html>',{url:'https://accordniche.pp.ua'+path,runScripts:'outside-only',pretendToBeVisual:true})
  const window=dom.window,calls=[]
  let mine=own
  window.scrollTo=()=>{}
  window.confirm=()=>true
  window.fetch=async(input,options={})=>{
    const url=new URL(input,window.location.href),method=options.method || 'GET'
    calls.push({url,method,options})
    if(url.pathname==='/api/web/session')return response({account:{signed_in:authenticated,has_session:true},csrf:'a'.repeat(48)})
    if(url.pathname==='/api/public/site-config')return response({})
    if(url.pathname==='/api/public/blog')return response({items:empty?[]:[article],total:empty?0:25,limit:12,offset:Number(url.searchParams.get('offset'))})
    if(url.pathname==='/api/public/blog/real-article' || alias&&url.pathname==='/api/public/blog/old-address')return response({...article,comments_enabled:!closed})
    if(url.pathname==='/api/public/blog/real-article/comments')return response({items:[root],total:1,limit:10,offset:0})
    if(url.pathname==='/api/web/blog/posts/5/mine')return response(mine)
    if(url.pathname==='/api/web/blog/posts/5/comments' && method==='POST'){
      const data=JSON.parse(options.body)
      mine=[{...root,id:12,body:data.body,status:'pending',version:1}]
      return response(mine[0])
    }
    if(url.pathname==='/api/web/blog/comments/12' && method==='PUT')return response({detail:'Коментар вже змінено; оновіть сторінку'},conflict?409:200)
    return response({},404)
  }
  window.eval(bundle)
  return {window,document:window.document,calls,close:()=>window.close()}
}

test('blog list uses API cards and server pagination, and empty blog has no invented posts',async()=>{
  const app=mount({path:'/blog?page=2&q=аромат'})
  try{
    await waitFor(()=>app.document.querySelector('.blog-card'))
    assert.equal(app.document.querySelector('.blog-card h2').textContent,article.title)
    assert.ok(app.calls.some(call=>call.url.pathname==='/api/public/blog' && call.url.searchParams.get('offset')==='12' && call.url.searchParams.get('q')==='аромат'))
    app.document.querySelector('.blog-card-link').click()
    await waitFor(()=>app.document.querySelector('.blog-prose'))
    assert.equal(app.window.location.pathname,'/blog/real-article')
  }finally{app.close()}
  const empty=mount({path:'/blog',empty:true})
  try{await waitFor(()=>empty.document.querySelector('.blog-state h2'));assert.equal(empty.document.querySelectorAll('.blog-card').length,0)}finally{empty.close()}
})

test('Markdown renders safely, comments remain plain text and guest sessions cannot comment',async()=>{
  const app=mount()
  try{
    await waitFor(()=>button(app.document,'Увійти та коментувати') && app.document.querySelector('.blog-comment p'))
    const prose=app.document.querySelector('.blog-prose')
    assert.equal(prose.querySelector('h2').textContent,'Корисний заголовок')
    assert.ok(prose.querySelector('strong'))
    assert.equal(prose.querySelectorAll('script,iframe,svg').length,0)
    assert.equal(prose.querySelectorAll('a[href^="javascript:"],img[src^="data:"]').length,0)
    assert.equal(prose.querySelector('img').getAttribute('src'),'/media/image-123.jpg')
    assert.equal(prose.querySelector('a[href^="https:"]').rel,'noopener noreferrer nofollow')
    assert.equal(app.document.querySelector('.blog-comment p').textContent,root.body)
    assert.equal(app.document.querySelector('.blog-comment img'),null)
    assert.equal(app.document.querySelector('.comment-form'),null)
    assert.equal(app.window.hacked,undefined)
  }finally{app.close()}
})

test('authenticated comment uses existing CSRF session and stays pending, outside public thread',async()=>{
  const app=mount({authenticated:true})
  try{
    await waitFor(()=>app.document.querySelector('.comment-form textarea'))
    input(app.window,app.document.querySelector('.comment-form textarea'),'Мій новий коментар')
    await waitFor(()=>!button(app.document,'Надіслати на модерацію').disabled)
    app.document.querySelector('.comment-form').dispatchEvent(new app.window.Event('submit',{bubbles:true,cancelable:true}))
    await waitFor(()=>app.document.querySelector('.own-comment'))
    assert.match(app.document.querySelector('.own-comment').textContent,/На модерації.*Мій новий коментар/s)
    assert.equal(app.document.querySelectorAll('.blog-comment').length,1)
    const sent=app.calls.find(call=>call.method==='POST')
    assert.equal(sent.options.credentials,'include')
    assert.equal(sent.options.headers['X-CSRF-Token'],'a'.repeat(48))
    assert.match(JSON.parse(sent.options.body).client_key,/^[a-z0-9-]{36}$/)
  }finally{app.close()}
})

test('closed discussion preserves approved comments while disabling the form',async()=>{
  const app=mount({authenticated:true,closed:true})
  try{
    await waitFor(()=>app.document.querySelector('.blog-comment'))
    assert.match(app.document.querySelector('.blog-comments').textContent,/Нові коментарі.*закрито/)
    assert.equal(app.document.querySelector('.comment-form'),null)
  }finally{app.close()}
})

test('editing conflict keeps the unsent comment in the editor',async()=>{
  const app=mount({authenticated:true,conflict:true,own:[{...root,id:12,body:'Мій текст',status:'approved',version:2}]})
  try{
    await waitFor(()=>button(app.document,'Редагувати'))
    button(app.document,'Редагувати').click()
    await waitFor(()=>app.document.querySelector('.comment-form textarea').value==='Мій текст')
    input(app.window,app.document.querySelector('.comment-form textarea'),'Збережіть моє редагування')
    await waitFor(()=>app.document.querySelector('.comment-form textarea').value==='Збережіть моє редагування')
    app.document.querySelector('.comment-form').dispatchEvent(new app.window.Event('submit',{bubbles:true,cancelable:true}))
    await waitFor(()=>app.document.querySelector('.shop-error'))
    assert.equal(app.document.querySelector('.comment-form textarea').value,'Збережіть моє редагування')
    assert.match(app.document.querySelector('.shop-error').textContent,/вже змінено/)
  }finally{app.close()}
})

test('historical slug resolves to current address and article metadata',async()=>{
  const app=mount({path:'/blog/old-address',alias:true})
  try{
    await waitFor(()=>app.window.location.pathname==='/blog/real-article' && app.document.title.startsWith(article.title))
    assert.equal(app.document.querySelector('meta[name="description"]').content,article.excerpt)
  }finally{app.close()}
})

test('blog pagination keeps the applied search until the search form is submitted',async()=>{
 const app=mount({path:'/blog?q=аромат'})
 try{
  await waitFor(()=>app.document.querySelector('.blog-card'))
  const field=app.document.querySelector('[aria-label="Пошук у блозі"]')
  Object.getOwnPropertyDescriptor(app.window.HTMLInputElement.prototype,'value').set.call(field,'чернетка запиту')
  field.dispatchEvent(new app.window.Event('input',{bubbles:true}))
  await new Promise(resolve=>setTimeout(resolve,20))
  button(app.document,'Далі →').click()
  await waitFor(()=>app.window.location.search.includes('page=2'))
  assert.equal(new URLSearchParams(app.window.location.search).get('q'),'аромат')
  await waitFor(()=>app.calls.some(call=>call.url.pathname==='/api/public/blog' && call.url.searchParams.get('offset')==='12'))
  assert.equal(app.calls.filter(call=>call.url.pathname==='/api/public/blog').at(-1).url.searchParams.get('q'),'аромат')
 }finally{app.close()}
})
