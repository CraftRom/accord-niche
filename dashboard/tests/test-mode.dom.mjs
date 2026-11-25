import test from 'node:test'
import assert from 'node:assert/strict'
import {fileURLToPath} from 'node:url'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'

const root=fileURLToPath(new URL('../',import.meta.url))
const page=await build({bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env.VITE_API_URL':'""','process.env.NODE_ENV':'"test"'},
  stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import TestModeCard from './src/components/TestModeCard';import {setSession} from './src/api';setSession({role:'admin',csrf_token:'a'.repeat(48)});createRoot(document.getElementById('root')).render(<TestModeCard/>);`,resolveDir:root,loader:'jsx'}})
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})
const button=(doc,text)=>[...doc.querySelectorAll('button')].find(node=>node.textContent.trim()===text)
async function waitFor(check){const until=Date.now()+4000;while(Date.now()<until){if(check())return;await new Promise(resolve=>setTimeout(resolve,15))}assert.ok(check(),'not ready')}

test('system administrator enables test mode, opens the signed link and turns it off',async()=>{
  const dom=new JSDOM('<html><body><div id="root"></div></body></html>',{url:'https://dashboard.accordniche.pp.ua/settings',runScripts:'outside-only',pretendToBeVisual:true})
  const window=dom.window,calls=[]
  window.Headers=Headers;window.scrollTo=()=>{};window.confirm=()=>true
  const on={active:true,created_by:'root',expires_at:'2026-11-25T22:00:00Z',aromas:10,products:30,posts:3,enter_url:'https://accordniche.pp.ua/api/public/test-mode/enter?token=abc.1.sig'}
  window.fetch=async(input,options={})=>{
    const url=new URL(input,window.location.href);calls.push({url,method:options.method||'GET',body:options.body?JSON.parse(options.body):null})
    if(url.pathname!=='/api/system/test-mode')return response({},404)
    if(options.method==='POST')return response(on)
    return response({active:false})
  }
  try{
    window.eval(page.outputFiles[0].text)
    await waitFor(()=>button(window.document,'Увімкнути тест-режим'))
    assert.match(window.document.body.textContent,/окремій тестовій базі/)
    const select=window.document.querySelector('[aria-label="Тривалість тест-режиму"]');select.value='4';select.dispatchEvent(new window.Event('change',{bubbles:true}))
    button(window.document,'Увімкнути тест-режим').click()
    await waitFor(()=>window.document.querySelector('a[href*="test-mode/enter"]'))
    assert.deepEqual(calls.find(call=>call.method==='POST').body,{hours:4})
    assert.match(window.document.body.textContent,/10 ароматів \(30 SKU\), 3 статті/)
    button(window.document,'Вимкнути').click()
    await waitFor(()=>calls.some(call=>call.method==='DELETE'))
  }finally{window.close()}
})
