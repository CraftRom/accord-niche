// Website motion: animation must never hide content, shift layout or ignore
// the system «reduce motion» setting.
import { chromium } from 'playwright'

const BASE = process.env.WEBSITE_URL || 'http://127.0.0.1:5175'
const variants = Array.from({ length: 12 }, (_, i) => ({ id: 100 + i, name: `Aroma ${i} 5 мл`, brand: 'BRAND', gender: 'unisex', volume_ml: 5, price: String(60 + i), stock: 5, photo_url: null }))
const aromas = variants.map((v, i) => ({ id: v.id, key: 'k' + i, name: `Аромат ${i}`, brand: 'BRAND', gender: 'unisex', variants: [v], categories: [], stock: 5, min_price: v.price, price_per_ml: '12', image: '', volumes: [5], is_new: i < 4, bestseller_rank: i < 4 ? i + 1 : null }))
function data(url) {
  const path = url.pathname
  if (path === '/api/web/session') return { account: { signed_in: false, has_session: true }, csrf: 'a'.repeat(48) }
  if (path === '/api/public/site-config') return {}
  if (path === '/api/public/storefront') return { hits: aromas.slice(0, 4), recommended: aromas.slice(4, 8), new_arrivals: aromas.slice(0, 4), selection: aromas, total: 12, available: 12, window_days: 90 }
  if (path === '/api/public/aromas') return { items: aromas, total: 12, limit: 24, offset: 0, brands: ['BRAND'], categories: [] }
  if (/^\/api\/public\/aromas\/\d+$/.test(path)) return { item: aromas[0], related: aromas.slice(1, 5) }
  if (path === '/api/public/products') return variants.filter((p) => (url.searchParams.get('ids') || '').split(',').includes(String(p.id)))
  return {}
}

const browser = await chromium.launch()
const failures = []
let checks = 0
const check = (ok, label) => { checks++; console.log(`${ok ? 'PASS' : 'FAIL'} ${label}`); if (!ok) failures.push(label) }
async function open(reducedMotion) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.addInitScript(() => {
    window.__shift = 0
    try { new PerformanceObserver((list) => { for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__shift += entry.value }).observe({ type: 'layout-shift', buffered: true }) } catch { /* unsupported */ }
  })
  await page.route('**/api/**', (route) => route.fulfill({ json: data(new URL(route.request().url())) }))
  return { page, context, errors }
}

try {
  // ------------------------------------------------------------ full motion
  {
    const { page, context, errors } = await open('no-preference')
    await page.goto(BASE + '/')
    await page.locator('.product-card').first().waitFor()
    await page.waitForTimeout(400)
    const aboveFoldHidden = await page.evaluate(() => [...document.querySelectorAll('.reveal-pending')].filter((el) => el.getBoundingClientRect().top < innerHeight).length)
    check(aboveFoldHidden === 0, 'nothing on the first screen is hidden for a reveal')
    const pending = await page.locator('.reveal-pending').count()
    check(pending > 0, `blocks below the fold wait to rise in (${pending})`)
    await page.waitForTimeout(1200)
    check(await page.evaluate(() => getComputedStyle(document.querySelector('#hero-title')).opacity === '1'), 'hero title settles fully visible')
    // Scroll through the page: every pending block must arrive and return to its plain state.
    for (let y = 0; y < 6000; y += 500) { await page.mouse.wheel(0, 500); await page.waitForTimeout(120) }
    await page.waitForTimeout(1500)
    check(await page.locator('.reveal-pending, .revealed').count() === 0, 'revealed blocks drop the reveal classes (hover keeps its own timing)')
    const invisible = await page.evaluate(() => [...document.querySelectorAll('.product-card, .section-row')].filter((el) => getComputedStyle(el).opacity !== '1').length)
    check(invisible === 0, 'after scrolling every card and section header is fully visible')
    check(await page.evaluate(() => window.__shift) < 0.05, `no layout shift from motion (CLS ${await page.evaluate(() => window.__shift.toFixed(3))})`)
    // Page transition: header stays named, navigation completes.
    check(await page.evaluate(() => getComputedStyle(document.querySelector('.header')).viewTransitionName) === 'site-header', 'header keeps its own view-transition name')
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.locator('#store-navigation a', { hasText: 'Каталог' }).click()
    await page.getByRole('heading', { name: 'Каталог', level: 1 }).waitFor()
    check(new URL(page.url()).pathname === '/catalog', 'navigation completes through the view transition')
    // Cart badge pops; drawer slides in.
    await page.locator('.product-card').first().click()
    await page.getByRole('button', { name: /ДОДАТИ В КОШИК/ }).click()
    await page.getByRole('dialog', { name: 'Кошик' }).waitFor()
    check(await page.evaluate(() => getComputedStyle(document.querySelector('.basket')).animationName) === 'accord-drawer', 'cart drawer slides in')
    check(await page.evaluate(() => getComputedStyle(document.querySelector('.cart-count')).animationName) === 'accord-pop', 'cart count pops when it changes')
    check(errors.length === 0, 'no runtime errors with motion ' + errors.join('; '))
    await context.close()
  }
  // ---------------------------------------------------------- reduced motion
  {
    const { page, context, errors } = await open('reduce')
    await page.goto(BASE + '/')
    await page.locator('.product-card').first().waitFor()
    await page.waitForTimeout(300)
    check(await page.locator('.reveal-pending').count() === 0, 'reduce motion: nothing is held back for a reveal')
    const animated = await page.evaluate(() => [...document.querySelectorAll('body *')].filter((el) => { const s = getComputedStyle(el); return s.animationName !== 'none' || parseFloat(s.transitionDuration) > 0 }).length)
    check(animated === 0, `reduce motion: no element animates or transitions (${animated})`)
    check(await page.evaluate(() => getComputedStyle(document.querySelector('#hero-title')).opacity === '1'), 'reduce motion: hero is visible at once')
    await page.locator('#store-navigation a', { hasText: 'Каталог' }).click()
    await page.getByRole('heading', { name: 'Каталог', level: 1 }).waitFor()
    check(errors.length === 0, 'no runtime errors with reduced motion ' + errors.join('; '))
    await context.close()
  }
} finally { await browser.close() }
console.log(`WEBSITE MOTION: ${checks - failures.length}/${checks}`)
if (failures.length) process.exitCode = 1
