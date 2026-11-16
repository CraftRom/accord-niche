import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync,readdirSync} from 'node:fs'
import {JSDOM,VirtualConsole} from 'jsdom'

test('production CSS keeps navigation text dark after all base styles are applied',()=>{
 const assets=new URL('../dist/assets/',import.meta.url)
 const file=readdirSync(assets).find(name=>/^index-.*\.css$/.test(name))
 assert.ok(file,'Build dashboard before testing production styles')
 const css=readFileSync(new URL(file,assets),'utf8')
 const errors=[],virtualConsole=new VirtualConsole()
 virtualConsole.on('jsdomError',error=>errors.push(error.message))
 const dom=new JSDOM('<!doctype html><style>'+css+'</style><nav class="nav commerce-navigation"><section class="nav-group"><a class="active">Огляд магазину</a></section></nav>',{virtualConsole})
 try{
  assert.deepEqual(errors,[])
  assert.equal(dom.window.getComputedStyle(dom.window.document.querySelector('a')).color,'rgb(25, 21, 15)')
 }finally{dom.window.close()}
})

test('active blog tabs keep readable contrast in the production theme',()=>{
 const assets=new URL('../dist/assets/',import.meta.url)
 const names=readdirSync(assets)
 const css=[...names.filter(name=>/^index-.*\.css$/.test(name)),...names.filter(name=>/^Blog-.*\.css$/.test(name))].map(name=>readFileSync(new URL(name,assets),'utf8')).join('\n')
 const dom=new JSDOM('<!doctype html><style>'+css+'</style><div class="blog-admin-tabs"><button class="btn" aria-selected="true">Публікації</button></div>')
 try{
  const style=dom.window.getComputedStyle(dom.window.document.querySelector('button'))
  function rgb(value){
   if(value.startsWith('var(')){
    const [,name,fallback]=value.match(/^var\((--[\w-]+),?\s*([^)]*)\)$/)
    return rgb(dom.window.getComputedStyle(dom.window.document.documentElement).getPropertyValue(name).trim() || fallback)
   }
   if(value.startsWith('#'))return value.slice(1).match(/.{2}/g).map(hex=>parseInt(hex,16)/255)
   return value.match(/[\d.]+/g).slice(0,3).map(Number).map(n=>n/255)
  }
  const luminance=value=>rgb(value).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4).reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0)
  // JSDOM does not resolve var() in background; read the selected rule's
  // declaration and resolve its theme variable before calculating contrast.
  const selected=[...dom.window.document.styleSheets].flatMap(sheet=>[...sheet.cssRules]).find(rule=>rule.selectorText==='.blog-admin-tabs [aria-selected=true]')
  assert.ok(selected,'Selected blog tab style is required')
  const a=luminance(style.color),b=luminance(selected.style.getPropertyValue('background'))
  assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5,'Selected tab text must have at least 4.5:1 contrast')
 }finally{dom.window.close()}
})
