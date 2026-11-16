import test from 'node:test'
import assert from 'node:assert/strict'
import {fileURLToPath} from 'node:url'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'

const root=fileURLToPath(new URL('../',import.meta.url))
const built=await build({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import Blog from './src/pages/Blog';import {setSession} from './src/api';setSession({role:'admin',csrf_token:'a'.repeat(48)});createRoot(document.getElementById('root')).render(<Blog/>);`,resolveDir:root,loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env.VITE_API_URL':'""','process.env.NODE_ENV':'"test"'}})
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})
const post={id:5,title:'Чернетка статті',slug:'article',excerpt:'Опис',author_name:'Редакція',status:'draft',published_at:null,comment_count:0}
const comment={id:9,post_id:5,post_title:post.title,author_name:'Покупець',body:'Очікує перевірки',status:'pending',version:1,created_at:'2026-11-16T09:00:00Z',moderation_note:'',parent_id:null}
const button=(doc,text)=>[...doc.querySelectorAll('button')].find(node=>node.textContent.trim()===text)
async function waitFor(check){const until=Date.now()+4000;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,15))}assert.ok(check(),'CMS did not become ready')}
function mount(){
 const dom=new JSDOM('<html><body><div id="root"></div></body></html>',{url:'https://dashboard.accordniche.pp.ua/blog',runScripts:'outside-only',pretendToBeVisual:true})
 const window=dom.window,calls=[];let finish,fail=false
 window.Headers=Headers;window.scrollTo=()=>{}
 window.fetch=async(input,options={})=>{
  const url=new URL(input,window.location.href);calls.push({url,options})
  if(url.pathname==='/api/blog/posts'){
   if(url.searchParams.get('status')==='published')return new Promise(resolve=>{finish=()=>resolve(response({items:[],total:0,pending_comments:0}))})
   return response({items:[post],total:1,pending_comments:1})
  }
  if(url.pathname==='/api/blog/comments'){
   if(url.searchParams.get('status')==='approved')return new Promise(resolve=>{finish=()=>resolve(response({detail:'Черга недоступна'},503))})
   if(fail)return response({detail:'Оновлення не вдалося'},503)
   return response({items:[comment],total:1})
  }
  return response({},404)
 }
 window.eval(built.outputFiles[0].text)
 return {window,document:window.document,calls,finish:()=>finish(),failRefresh:()=>{fail=true},close:()=>window.close()}
}

test('changing post filters hides old cards while the matching results load',async()=>{
 const app=mount()
 try{
  await waitFor(()=>app.document.querySelector('.blog-admin-posts h2'))
  const select=app.document.querySelector('[aria-label="Стан статей"]');select.value='published';select.dispatchEvent(new app.window.Event('change',{bubbles:true}))
  await waitFor(()=>app.calls.some(call=>call.url.searchParams.get('status')==='published'))
  assert.equal(Boolean(app.document.querySelector('.blog-admin-posts h2')),false)
  app.finish();await waitFor(()=>app.document.body.textContent.includes('Публікацій поки немає'))
 }finally{app.close()}
})

test('moderation filter errors never leave the previous queue actionable',async()=>{
 const app=mount()
 try{
  await waitFor(()=>[...app.document.querySelectorAll('[role="tab"]')].some(node=>node.textContent.startsWith('Коментарі')))
  ;[...app.document.querySelectorAll('[role="tab"]')].find(node=>node.textContent.startsWith('Коментарі')).click()
  await waitFor(()=>button(app.document,'Схвалити'))
  const select=app.document.querySelector('[aria-label="Стан коментарів"]');select.value='approved';select.dispatchEvent(new app.window.Event('change',{bubbles:true}))
  await waitFor(()=>app.calls.some(call=>call.url.pathname==='/api/blog/comments'&&call.url.searchParams.get('status')==='approved'))
  app.finish();await waitFor(()=>app.document.body.textContent.includes('Черга недоступна'))
  assert.equal(Boolean(button(app.document,'Схвалити')),false)
  assert.doesNotMatch(app.document.body.textContent,/Черга порожня/)
 }finally{app.close()}
})

test('same-filter refresh failure preserves the loaded moderation queue with an error',async()=>{
 const app=mount()
 try{
  await waitFor(()=>app.document.querySelector('[role="tab"]'))
  ;[...app.document.querySelectorAll('[role="tab"]')].find(node=>node.textContent.startsWith('Коментарі')).click()
  await waitFor(()=>button(app.document,'Схвалити'))
  app.failRefresh();button(app.document,'Оновити').click()
  await waitFor(()=>app.document.body.textContent.includes('Оновлення не вдалося'))
  assert.ok(button(app.document,'Схвалити'))
 }finally{app.close()}
})
