// UI-029: elfar:* browser storage moves to accord:* without losing what a
// manager saved (chat drafts, notification settings, volume).
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync,readdirSync,statSync} from 'node:fs'
import {join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {build} from 'esbuild'

const root=fileURLToPath(new URL('../',import.meta.url))
const code=(await build({stdin:{contents:"export * from './src/storageKeys'",resolveDir:root,loader:'js'},bundle:true,write:false,format:'esm',logLevel:'silent'})).outputFiles[0].text
const {migrateLegacyStorage,STORAGE}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'))

function memory(entries={}){
  const map=new Map(Object.entries(entries))
  return {get length(){return map.size},key:i=>[...map.keys()][i]??null,getItem:k=>map.has(k)?map.get(k):null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k),dump:()=>Object.fromEntries(map)}
}

test('settings, volume and every chat draft move to the accord keys',()=>{
  const scope='a'.repeat(64)
  const s=memory({
    'elfar:notification-settings':'{"sound":true}',
    'elfar:notification-device-volume':'150',
    'elfar:notification-nudge-dismissed':'1',
    'elfar:notification-leader':'{"id":"x"}',
    'elfar:chunk-reload':'1',
    'elfar:chat-draft:v1:active':`{"scope":"${scope}"}`,
    [`elfar:chat-draft:v1:${scope}:order:7`]:'{"text":"Привіт"}',
    'shop_dashboard_token':'keep',
  })
  assert.equal(migrateLegacyStorage(s),5)
  assert.deepEqual(s.dump(),{
    'shop_dashboard_token':'keep',
    [STORAGE.notificationSettings]:'{"sound":true}',
    [STORAGE.notificationVolume]:'150',
    [STORAGE.notificationNudge]:'1',
    'accord:chat-draft:v1:active':`{"scope":"${scope}"}`,
    [`accord:chat-draft:v1:${scope}:order:7`]:'{"text":"Привіт"}',
  })
})

test('a value already saved under the new key is newer and wins',()=>{
  const s=memory({'elfar:notification-device-volume':'50',[STORAGE.notificationVolume]:'120'})
  assert.equal(migrateLegacyStorage(s),0)
  assert.deepEqual(s.dump(),{[STORAGE.notificationVolume]:'120'})
})

test('running twice is harmless and blocked storage never throws',()=>{
  const s=memory({'elfar:notification-device-volume':'90'})
  migrateLegacyStorage(s);assert.equal(migrateLegacyStorage(s),0)
  assert.equal(migrateLegacyStorage({get length(){throw new Error('SecurityError')}}),0)
  assert.equal(migrateLegacyStorage(null),0)
})

test('the migration runs before the app and no elfar names are left in the dashboard',()=>{
  const main=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8')
  assert.match(main.split('\n')[0],/^import '\.\/storageMigration'$/)
  const allowed=new Set(['storageKeys.js','ManagedTable.jsx'])
  // Deliberate mentions of the neighbouring ELFAR shop: it shares the server
  // (a restore does not stop it) and names the SalesDrive form base.
  const deliberate=[/ELFAR не зупиняється/g,/«ELFAR — Telegram Bot»/g]
  const offenders=[]
  const walk=dir=>{for(const name of readdirSync(dir)){const path=join(dir,name);if(statSync(path).isDirectory())walk(path);else if(/\.(jsx?|css)$/.test(name)&&!allowed.has(name)){const text=deliberate.reduce((t,re)=>t.replace(re,''),readFileSync(path,'utf8'));if(/elfar/i.test(text))offenders.push(path)}}}
  walk(fileURLToPath(new URL('../src/',import.meta.url)))
  assert.deepEqual(offenders,[])
})
