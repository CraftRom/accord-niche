// Main website (W-12 / W-32): the buyer's path — home, catalog, product,
// cart, checkout, profile, blog — at 320, 390, 768 and 1280 px. Besides the
// shared structure checks (h1, overflow, accessible names, ids, 24 px
// targets) it measures the contrast of every rendered text against the
// background really behind it and flags functional text below 12 px.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { auditPage, auditText } from './a11y-audit.mjs'

const BASE = process.env.WEBSITE_URL || 'http://127.0.0.1:5175'
const output = process.env.QA_OUTPUT_DIR || 'qa/output'
mkdirSync(output, { recursive: true })

const variants = [
  { id: 42, name: 'Actual Aroma 2 мл', brand: 'DB BRAND', gender: 'unisex', volume_ml: 2, price: '40', stock: 4, photo_url: null, is_new: true },
  { id: 43, name: 'Actual Aroma 5 мл', brand: 'DB BRAND', gender: 'unisex', volume_ml: 5, price: '75', stock: 2, photo_url: null, is_new: true },
]
const aroma = { id: 42, key: 'db:actual', name: 'Actual Aroma з дуже довгою назвою для вузького екрана', brand: 'DB BRAND', gender: 'unisex', description: 'Опис із каталогу. '.repeat(8), variants, categories: [], stock: 6, min_price: '40', price_per_ml: '15', image: '', volumes: [2, 5], is_new: true, bestseller_rank: 1 }
const other = { ...aroma, id: 60, key: 'other:real', name: 'Other Real Aroma', brand: 'OTHER', variants: [{ ...variants[0], id: 60, brand: 'OTHER' }], bestseller_rank: null }
const article = { id: 5, slug: 'real-article', title: 'Стаття з бази', excerpt: 'Опис із редактора', author_name: 'Автор редакції', cover_url: '', published_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-01T10:00:00Z', reading_minutes: 2, comment_count: 0, comments_enabled: true, body: '## Заголовок\n\nТекст статті.' }

function data(url) {
  const path = url.pathname
  if (path === '/api/web/session') return { account: { signed_in: false, has_session: true, account_key: 'guest' }, csrf: 'a'.repeat(48) }
  if (path === '/api/public/site-config') return { phone: '+380501234567', seller_name: 'Продавець із БД' }
  if (path === '/api/public/storefront') return { hits: [aroma], recommended: [other], new_arrivals: [aroma], selection: [aroma, other], total: 2, available: 2, window_days: 90 }
  if (/^\/api\/public\/aromas\/\d+$/.test(path)) return { item: aroma, related: [other] }
  if (path === '/api/public/aromas') return { items: [aroma, other], total: 2, limit: 24, offset: 0, brands: ['DB BRAND', 'OTHER'], categories: [], updated_at: '2026-11-18T08:00:00Z' }
  if (path === '/api/public/products') return variants.filter((p) => (url.searchParams.get('ids') || '').split(',').includes(String(p.id)))
  if (path === '/api/public/blog') return { items: [article], total: 1, limit: 12, offset: 0 }
  if (path === '/api/public/blog/real-article') return article
  if (path === '/api/public/blog/real-article/comments') return { items: [], total: 0, limit: 10, offset: 0 }
  if (path === '/api/web/delivery/config') return { courier_enabled: true, novaposhta_enabled: true }
  if (path === '/api/web/checkout/defaults') return {}
  if (path === '/api/web/checkout/quote') return { subtotal: '40', discount: '0', bonus_used: '0', bonus_available: '0', total: '40', quote_token: 'a'.repeat(64), items: [{ product_id: 42, qty: 1, unit_price: '40', line_total: '40' }] }
  if (path === '/api/web/profile') return { orders_count: 0, bonus_balance: 0 }
  if (path === '/api/web/orders') return { items: [], total: 0, limit: 10, offset: 0 }
  return {}
}

const SCREENS = [
  { name: 'home', path: '/' },
  { name: 'catalog', path: '/catalog' },
  { name: 'product', path: '/aroma/42' },
  { name: 'cart', path: '/', open: async (page) => { await page.getByRole('button', { name: /Кошик/ }).first().click(); await page.getByRole('dialog').waitFor() } },
  { name: 'checkout', path: '/checkout' },
  { name: 'profile', path: '/profile' },
  { name: 'blog', path: '/blog' },
  { name: 'article', path: '/blog/real-article' },
]

const browser = await chromium.launch()
const failures = []
let checks = 0
const check = (ok, label) => { checks++; console.log(`${ok ? 'PASS' : 'FAIL'} ${label}`); if (!ok) failures.push(label) }
try {
  for (const width of [320, 390, 768, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 860 } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.addInitScript(() => { try { localStorage.setItem('accord:niche:cart', JSON.stringify({ 42: 1 })) } catch { /* storage blocked */ } })
    await page.route('**/api/**', (route) => route.fulfill({ json: data(new URL(route.request().url())) }))
    await page.route('https://accounts.google.com/**', (route) => route.fulfill({ body: '' }))
    const cdp = await page.context().newCDPSession(page)
    for (const screen of SCREENS) {
      const label = `${width}px ${screen.name}`
      errors.length = 0
      await page.goto(BASE + screen.path)
      await page.locator('h1').first().waitFor({ state: 'attached' })
      await page.waitForLoadState('networkidle')
      if (screen.open) await screen.open(page)
      await page.waitForTimeout(300) // let entrance animations settle before measuring colour
      await auditPage(page, cdp, label, check, { errors })
      await auditText(page, label, check)
      if (width === 320 || width === 1280) await page.screenshot({ path: `${output}/website-a11y-${screen.name}-${width}.png` })
    }
    await page.close()
  }
} finally { await browser.close() }
console.log(`WEBSITE A11Y MATRIX: ${checks - failures.length}/${checks}`)
if (failures.length) process.exitCode = 1
