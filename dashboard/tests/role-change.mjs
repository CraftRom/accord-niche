// UI-022: a role change states what access is lost or gained before saving.
import test from 'node:test'
import assert from 'node:assert/strict'
import {fileURLToPath} from 'node:url'
import {build} from 'esbuild'

const root=fileURLToPath(new URL('../',import.meta.url))
const code=(await build({stdin:{contents:"export {roleChange} from './src/pages/Operators'",resolveDir:root,loader:'js'},bundle:true,write:false,format:'esm',jsx:'automatic',loader:{'.css':'empty','.js':'jsx'},define:{'import.meta.env.VITE_API_URL':'""','process.env.NODE_ENV':'"test"'},logLevel:'silent'})).outputFiles[0].text
const {roleChange}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'))

test('downgrading an administrator lists exactly the access that goes away',()=>{
  assert.deepEqual(roleChange('shop_admin','operator'),{lost:['Налаштування магазину й модулі','Облікові записи менеджерів'],gained:[]})
})
test('promoting a manager lists what is added and nothing lost',()=>{
  assert.deepEqual(roleChange('operator','shop_admin'),{lost:[],gained:['Налаштування магазину й модулі','Облікові записи менеджерів']})
})
test('unknown roles never invent access',()=>{
  assert.deepEqual(roleChange('ghost','ghost'),{lost:[],gained:[]})
})
