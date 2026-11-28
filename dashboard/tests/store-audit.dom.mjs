import test from 'node:test'
import assert from 'node:assert/strict'
import {fileURLToPath} from 'node:url'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'
import {canAccessPage} from '../src/roles.js'
import {navigationFor} from '../src/commerce.js'

test('only administrative roles see and open the audit pages',()=>{
  for(const role of ['admin','shop_admin','operator']){
    assert.equal(canAccessPage(role,'/store-audit/security'),role!=='operator')
    assert.equal(navigationFor(role).some(g=>g.items.some(i=>i.to==='/store-audit')),role!=='operator')
  }
})

test('release view keeps pending checks visible and links to the blocker list',async()=>{
  const root=fileURLToPath(new URL('../',import.meta.url))
  const built=await build({stdin:{contents:`
    import {createRoot} from 'react-dom/client'
    import {MemoryRouter,Routes,Route} from 'react-router-dom'
    import Audit from './src/pages/StoreAudit'
    createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={['/store-audit/release']}>
      <Routes><Route path="/store-audit/:view" element={<Audit/>}/></Routes></MemoryRouter>)`,
    resolveDir:root,loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',
    loader:{'.css':'empty'},define:{'import.meta.env.VITE_API_URL':'""','process.env.NODE_ENV':'"test"'}})
  const dom=new JSDOM('<div id="root"></div>',{url:'https://dashboard.accordniche.pp.ua',runScripts:'outside-only'})
  const {window}=dom
  window.Headers=Headers
  window.fetch=async()=>new Response(JSON.stringify({ready:false,blockers:['cart'],items:[
    {id:'cart',status:'open',type:'manual',details:{title:'Тест кошика',module:'orders',priority:'P1',assessment:'assumption'}}]}))
  try {
    window.eval(built.outputFiles[0].text)
    for(let i=0;i<100 && !window.document.querySelector('article');i++) await new Promise(r=>setTimeout(r,30))
    assert.match(window.document.body.textContent,/Готовність не підтверджено/)
    assert.equal(window.document.querySelectorAll('nav a').length,13)
    assert.match(window.document.querySelector('article').textContent,/Тест кошика/)
    assert.ok(window.document.querySelector('a[href="/store-audit/blockers"]'))
  } finally { window.close() }
})
