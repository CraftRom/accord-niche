import test from 'node:test'
import assert from 'node:assert/strict'
import {fileURLToPath} from 'node:url'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'

const root=fileURLToPath(new URL('../',import.meta.url))
const options={bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env.VITE_API_URL':'""','process.env.NODE_ENV':'"test"'}}
const checks=await build({...options,stdin:{contents:`import {seoChecks} from './src/pages/Blog';window.seoChecks=seoChecks`,resolveDir:root,loader:'jsx'}})
const page=await build({...options,stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import {CommentQueue} from './src/pages/BlogModeration';import {setSession} from './src/api';setSession({role:'admin',csrf_token:'a'.repeat(48)});createRoot(document.getElementById('root')).render(<CommentQueue/>);`,resolveDir:root,loader:'jsx'}})
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})
const button=(doc,text)=>[...doc.querySelectorAll('button')].find(node=>node.textContent.trim()===text)
async function waitFor(check){const until=Date.now()+4000;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,15))}assert.ok(check(),'not ready')}

test('SEO checklist rewards a complete article and flags what is missing',()=>{
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'outside-only'})
  dom.window.eval(checks.outputFiles[0].text)
  const words=Array.from({length:320},(_, i)=>'слово'+i).join(' ')
  const good={title:'Як обрати нішевий аромат для осені та зими',slug:'yak-obraty',excerpt:'Як обрати нішевий аромат: ноти, концентрація, стійкість і як спробувати аромат на розпив перед покупкою флакона.',
    body:'Як обрати нішевий аромат правильно — пояснюємо.\n\n## Ноти\n'+words+'\n\n[Каталог](/catalog)\n\n![Флакон Creed](/media/a.jpg)',
    cover_url:'/media/c.jpg',cover_alt:'Флакони',seo_title:'',seo_description:'',focus_keyword:'нішевий аромат',noindex:false}
  const result=JSON.parse(JSON.stringify(dom.window.seoChecks(good)))
  assert.deepEqual(result.filter(([,ok])=>!ok).map(([label])=>label),[])
  const weak=JSON.parse(JSON.stringify(dom.window.seoChecks({...good,focus_keyword:'',body:'Коротко ![Опис зображення](/media/a.jpg)',cover_alt:''})))
  const missing=weak.filter(([,ok])=>!ok).map(([label])=>label).join('|')
  for(const label of ['Ключова фраза задана','Є підзаголовки','Обкладинка з alt-текстом','Усі зображення в тексті мають опис','Є посилання на каталог'])assert.match(missing,new RegExp(label))
  dom.window.close()
})

test('moderators can select comments, delete them in bulk and ban an author',async()=>{
  const dom=new JSDOM('<html><body><div id="root"></div></body></html>',{url:'https://dashboard.accordniche.pp.ua/blog',runScripts:'outside-only',pretendToBeVisual:true})
  const window=dom.window,calls=[]
  window.Headers=Headers;window.scrollTo=()=>{};window.confirm=()=>true
  const comment=(id,extra={})=>({id,post_id:5,post_title:'Стаття',post_slug:'s',author_name:'Покупець',author_user_id:3,body:'Текст '+id,status:'pending',version:1,created_at:'2026-11-16T09:00:00Z',moderation_note:'',moderated_by:null,parent_id:null,flags:'',author_banned:false,author_approved:0,author_rejected:0,...extra})
  window.fetch=async(input,options={})=>{
    const url=new URL(input,window.location.href);calls.push({url,options,body:options.body?JSON.parse(options.body):null})
    if(url.pathname==='/api/blog/comments')return response({items:[comment(1,{flags:'link,contact'}),comment(2)],total:2,counts:{pending:2,approved:0,rejected:0,deleted:0}})
    if(url.pathname==='/api/blog/comments/bulk')return response({changed:2})
    if(url.pathname==='/api/blog/bans')return response({user_id:3,author_name:'Покупець',reason:'',banned_by:'owner',expires_at:null,created_at:'2026-11-16T09:00:00Z',comment_count:2},201)
    return response({},404)
  }
  try{
    window.eval(page.outputFiles[0].text)
    await waitFor(()=>window.document.querySelectorAll('.blog-moderation-item').length===2)
    assert.match(window.document.body.textContent,/Посилання/)
    assert.match(window.document.body.textContent,/Контакти/)
    assert.match(window.document.body.textContent,/На модерації \(2\)/)
    window.document.querySelector('[aria-label="Вибрати всі на сторінці"]').click()
    await waitFor(()=>window.document.body.textContent.includes('Вибрано: 2'))
    ;[...window.document.querySelectorAll('.blog-bulk-bar button')].find(node=>node.textContent==='Видалити').click()
    await waitFor(()=>calls.some(call=>call.url.pathname==='/api/blog/comments/bulk'))
    assert.deepEqual(calls.find(call=>call.url.pathname==='/api/blog/comments/bulk').body,{ids:[1,2],action:'delete'})
    await waitFor(()=>button(window.document,'Заблокувати автора') && !button(window.document,'Заблокувати автора').disabled)
    button(window.document,'Заблокувати автора').click()
    await waitFor(()=>window.document.querySelector('.blog-ban-form'))
    const reason=window.document.querySelector('[aria-label="Причина блокування"]')
    const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set
    setter.call(reason,'Спам');reason.dispatchEvent(new window.Event('input',{bubbles:true}))
    button(window.document,'Заблокувати').click()
    await waitFor(()=>calls.some(call=>call.url.pathname==='/api/blog/bans'))
    assert.deepEqual(calls.find(call=>call.url.pathname==='/api/blog/bans').body,{user_id:3,reason:'Спам',days:30,comments:'hide'})
  }finally{window.close()}
})
