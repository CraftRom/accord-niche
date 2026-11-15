import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFileSync, existsSync } from 'node:fs'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) }
catch { ({ chromium } = require(`${process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES}/playwright`)) }
const fixture = JSON.parse(execFileSync(process.env.PY || 'python3', ['-c', `
import json
from api.auth import Principal
from api.browser_sessions import profile
from api.routers.settings import _out
from shop.entities import OperatorRole
from shop.services.shop_settings import ShopSettings
profiles={r.value:profile(Principal('test','QA '+r.value,r,0 if r==OperatorRole.SYSADMIN else (1 if r==OperatorRole.ADMIN else 2)), 'qa-csrf') for r in OperatorRole}
print(json.dumps({'profiles':profiles,'settings':_out(ShopSettings.from_env()).model_dump(mode='json')}))
`], { cwd: root, env: { ...process.env, PYTHONPATH: resolve(root, 'backend') }, encoding: 'utf8' }))
const base = resolve(root, 'dashboard/dist')
assert.ok(existsSync(resolve(base, 'index.html')), 'Build dashboard before the browser test')
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }
const server = createServer((request, response) => {
  let file = resolve(base, '.' + new URL(request.url, 'http://localhost').pathname)
  if (!file.startsWith(base + sep)) file = resolve(base, 'index.html')
  if (!existsSync(file) || !extname(file)) file = resolve(base, 'index.html')
  response.setHeader('Content-Type', mime[extname(file)] || 'application/octet-stream')
  response.end(readFileSync(file))
})
await new Promise((done) => server.listen(0, '127.0.0.1', done))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, ...(process.env.QA_CHROME ? { executablePath: process.env.QA_CHROME } : {}) })
const errors = []
let checks = 0
async function session(role) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()
  page.on('pageerror', (error) => errors.push(error.message))
  const calls = []
  const writes = []
  let settings = { ...fixture.settings }
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.slice(4)
    calls.push(path)
    let data = {}
    if (path === '/auth/session') data = fixture.profiles[role]
    else if (path === '/stats/badges') data = { orders_new: 0, support_unread: 0 }
    else if (path === '/settings') {
      if (role === 'operator') return route.fulfill({ status: 403, json: { detail: 'Forbidden' } })
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON()
        assert.ok(Object.keys(body).every((key) => fixture.profiles[role].editable_settings.includes(key)))
        writes.push(body)
        settings = { ...settings, ...body }
      }
      data = settings
    } else if (path === '/operators') data = [
      { id: 1, login: 'administrator', name: 'Admin', role: 'shop_admin', is_active: true },
      { id: 2, login: 'manager', name: 'Manager', role: 'operator', is_active: true },
    ]
    else if (path === '/notifications/poll') data = { items: [], unread_count: 0 }
    else if (path === '/realtime/orders') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': ping\n\n' })
    return route.fulfill({ json: data })
  })
  return { page, context, calls, writes }
}
try {
  const manager = await session('operator')
  for (const path of ['/settings', '/operators', '/logs', '/backups']) {
    await manager.page.goto(origin + path)
    await manager.page.getByRole('heading', { name: 'Недостатньо прав' }).waitFor()
    assert.equal(await manager.page.locator('nav a[href="/settings"]').count(), 0)
    assert.equal(await manager.page.locator('nav a[href="/operators"]').count(), 0)
    assert.equal(await manager.page.locator('nav a[href="/orders"]').count(), 1)
    checks++
  }
  assert.equal(manager.calls.filter((path) => path.startsWith('/settings') || path.startsWith('/operators')).length, 0)
  checks++
  await manager.context.close()
  const admin = await session('shop_admin')
  await admin.page.goto(origin + '/settings')
  await admin.page.getByRole('searchbox', { name: 'Пошук налаштувань' }).fill('SalesDrive')
  await admin.page.getByRole('switch', { name: 'SalesDrive', exact: true }).check()
  assert.equal(await admin.page.getByRole('button', { name: 'Оновити дані SalesDrive' }).count(), 0)
  await admin.page.getByRole('button', { name: 'Зберегти', exact: true }).first().click()
  await admin.page.waitForFunction(() => document.body.textContent.includes('Налаштування збережено'))
  assert.deepEqual(admin.writes, [{ salesdrive_enabled: true }])
  checks++
  await admin.page.goto(origin + '/operators')
  await admin.page.getByRole('heading', { name: 'Команда та доступ' }).waitFor()
  await admin.page.getByRole('button', { name: 'Новий обліковий запис', exact: true }).click()
  assert.deepEqual(await admin.page.locator('select option').allTextContents(), ['Менеджер'])
  checks++
  await admin.context.close()
  const sysadmin = await session('admin')
  await sysadmin.page.goto(origin + '/operators')
  await sysadmin.page.getByRole('button', { name: 'Новий обліковий запис', exact: true }).click()
  assert.deepEqual(await sysadmin.page.locator('select option').allTextContents(), ['Менеджер', 'Адміністратор'])
  checks++
  await sysadmin.context.close()
  assert.deepEqual(errors, [])
  console.log(`PASS: ${checks} browser group/access scenarios; no page errors`)
} finally {
  await browser.close()
  await new Promise((done) => server.close(done))
}
