// Website audit stage 5: home first screen and facts (W-16, W-17), profile
// cards (W-22), order stages and tracking (W-23), article reading (W-24),
// comment states (W-25), footer groups (W-26), one state system (W-27).
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { auditPage, auditText } from './a11y-audit.mjs'

const output = process.env.QA_OUTPUT_DIR || 'qa/output'
mkdirSync(output, { recursive: true })

const BASE = process.env.WEBSITE_URL || 'http://127.0.0.1:5175'
const variant = (id, ml, price) => ({ id, name: `Aroma ${ml} мл`, brand: 'BRAND', gender: 'unisex', volume_ml: ml, price: String(price), stock: 3, photo_url: null })
const aroma = { id: 42, key: 'a', name: 'Aroma', brand: 'BRAND', gender: 'unisex', variants: [variant(42, 2, 40), variant(43, 5, 90)], categories: [], stock: 6, min_price: '40', price_per_ml: '18', image: '', volumes: [2, 5], is_new: true, bestseller_rank: 1 }
const other = { ...aroma, id: 60, key: 'b', volumes: [10], variants: [variant(60, 10, 160)], bestseller_rank: null }
const orders = [
  { id: 11, total: '130', status: 'shipped', status_source: 'local', status_label: 'Відправлене', tracking_number: '20451234567890', items: [{ name: 'Aroma 5 мл', qty: 1, price: '90' }], created_at: '2026-11-10T10:00:00Z', can_cancel: false },
  { id: 12, total: '40', status: 'new', status_source: 'crm', status_label: 'Очікує дзвінка', tracking_number: 'ABC-1', items: [], created_at: '2026-11-11T10:00:00Z', can_cancel: true },
  { id: 13, total: '40', status: 'cancelled', status_source: 'local', status_label: 'Скасоване', items: [], created_at: '2026-11-12T10:00:00Z', can_cancel: false },
]
const post = { id: 5, slug: 'note', title: 'Стаття', excerpt: 'Опис', author_name: 'Редакція', cover_url: '', published_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-01T10:00:00Z', reading_minutes: 3, comment_count: 1, comments_enabled: true,
  body: '## Розділ\n\nДовгий текст статті без пробілів: ' + 'https://example.com/' + 'дуже-довга-адреса-'.repeat(12) + '\n\n> Цитата редакції\n\n- перший\n- другий' }

function routes(page, { signedIn: startSignedIn = false, offline = false } = {}) {
  let signedIn = startSignedIn
  return page.route('**/api/**', (route) => {
    const url = new URL(route.request().url()), path = url.pathname
    if (offline && path === '/api/public/storefront') return route.abort('internetdisconnected')
    const json = (data) => route.fulfill({ json: data })
    if (path === '/api/web/auth/logout') { signedIn = false; return json({}) }
    if (path === '/api/web/session') return json({ account: signedIn ? { signed_in: true, has_session: true, account_key: 'k1', name: 'Олена', email: 'o@example.com', phone_verified: false, telegram_linked: false } : { signed_in: false, has_session: true, account_key: 'guest' }, csrf: 'a'.repeat(48), google_client_id: '', phone_verification_enabled: true, phone_sms_enabled: true, phone_telegram_enabled: true })
    if (path === '/api/public/site-config') return json({ phone: '+380501234567', email: 'shop@example.com', seller_name: 'ФОП Продавець', terms_url: 'https://accordniche.pp.ua/terms', instagram_url: 'https://instagram.com/accord' })
    if (path === '/api/public/storefront') return json({ hits: [aroma], recommended: [other], new_arrivals: [aroma], selection: [aroma, other], total: 2, available: 2, window_days: 90 })
    if (path === '/api/public/aromas') return json({ items: [aroma, other], total: 2, limit: 24, offset: 0, brands: ['BRAND'], categories: [] })
    if (path === '/api/public/legal/terms') return json({ key: 'terms', title: 'Публічна оферта', body: '## 1. Загальні положення\n\nПродавець — ФОП Продавець.', updated_at: null, seller_ready: true })
    if (path === '/api/web/profile') return json({ orders_count: 3, bonus_balance: 0 })
    if (path === '/api/web/orders') return json({ items: orders, has_more: false })
    if (path === '/api/public/blog/note') return json(post)
    if (path === '/api/public/blog/note/comments') return json({ items: [{ id: 1, author_name: 'Ігор', body: 'Дякую', created_at: '2026-11-02T10:00:00Z', reply_count: 0 }], total: 1 })
    if (path === '/api/web/blog/posts/5/mine') return json([{ id: 9, status: 'pending', body: 'Мій відгук', version: 1 }, { id: 10, status: 'rejected', body: 'Інший', version: 1 }])
    return json({})
  })
}

const browser = await chromium.launch()
const failures = []
let checks = 0
const check = (ok, label) => { checks++; console.log(`${ok ? 'PASS' : 'FAIL'} ${label}`); if (!ok) failures.push(label) }
async function open(options = {}, viewport = { width: 1280, height: 900 }) {
  const context = await browser.newContext({ viewport, reducedMotion: 'reduce' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await routes(page, options)
  return { page, context, errors }
}

try {
  // ------------------------------------------------------------ home, footer
  {
    const { page, context, errors } = await open()
    await page.goto(BASE + '/')
    await page.locator('.product-card').first().waitFor()
    const hero = page.locator('.hero-content')
    check(await hero.locator('.btn.primary').count() === 1 && await hero.locator('.btn.outline').count() === 0, 'W-16: the first screen has one dominant action')
    check((await page.locator('.hero-formats').textContent()).includes('2 / 5 / 10 мл'), 'W-16: formats line comes from the live assortment')
    check(await hero.getByRole('link', { name: 'ОБРАТИ АРОМАТ' }).getAttribute('href') === '/catalog', 'W-16: main action is a real link to the catalog')
    const facts = page.locator('.buyer-facts article')
    check(await facts.count() === 4, 'W-17: four facts before ordering')
    check(!/(сертифік|гаранті|100%|оригінальн[аі] гарант)/i.test(await page.locator('.buyer-facts').textContent()), 'W-17: no unproven guarantees or certificates')
    // Stage 6 polish: one icon scale (W-35), one badge height, uncropped bottles (W-38), one voice (W-37).
    const icons = await page.locator('.header-actions svg').evaluateAll((nodes) => nodes.map((n) => `${n.getAttribute('width')}x${n.getAttribute('height')}`))
    check(icons.length >= 3 && icons.every((size) => size === '20x20'), `W-35: header icons share one 20 px size (${icons.join(', ')})`)
    const badges = await page.locator('.product-badges > span').evaluateAll((nodes) => [...new Set(nodes.map((n) => Math.round(n.getBoundingClientRect().height)))])
    check(badges.length === 1 && badges[0] >= 24, `W-35: badges share one height (${badges.join(', ')} px)`)
    check(await page.evaluate(() => getComputedStyle(document.createElement('img')) && [...document.querySelectorAll('.photo-tile > img')].every((img) => getComputedStyle(img).objectFit === 'contain')), 'W-38: product photos are never cropped')
    check(!/(?<![\p{L}])(твій|твоє|твоїм|Знайди|Обери|Увійди|Спробуй)(?![\p{L}])/u.test(await page.locator('body').textContent()), 'W-37: the site speaks to the buyer formally, like the Mini App and the bot')
    // Menu: larger text, and the open section is marked for eyes and screen readers.
    const navSize = await page.locator('#store-navigation a').first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
    check(navSize >= 14, `menu text is at least 14 px (${navSize})`)
    check(await page.locator('#store-navigation [aria-current="page"]').count() === 0, 'menu: home page marks no section')
    await page.locator('#store-navigation a', { hasText: 'Хіти' }).click()
    await page.waitForURL('**/catalog?kind=hits')
    const current = page.locator('#store-navigation [aria-current="page"]')
    check(await current.count() === 1 && await current.textContent() === 'Хіти', 'menu: the open section is marked (Хіти, not Каталог)')
    const mark = await current.evaluate((el) => ({ weight: getComputedStyle(el).fontWeight, bar: getComputedStyle(el, '::after').transform }))
    check(Number(mark.weight) >= 600 && mark.bar !== 'none' && !mark.bar.startsWith('matrix(0'), 'menu: the open section is bold and underlined')
    await page.goto(BASE + '/')
    await page.locator('.product-card').first().waitFor()
    const footer = page.locator('.footer')
    check(await footer.locator('h2').allTextContents().then((t) => t.join('|')) === 'Покупцям|Про магазин|Підтримка|Документи', 'W-26: footer has four groups')
    check(await footer.getByRole('link', { name: 'Публічна оферта' }).getAttribute('href') === '/terms' && await footer.getByRole('link', { name: 'Політика конфіденційності' }).getAttribute('href') === '/privacy', 'W-26: documents are the shop\'s own pages')
    await footer.getByRole('button', { name: 'Доставка й оплата' }).click()
    check(await page.getByRole('dialog', { name: 'Доставка й оплата' }).isVisible(), 'W-26: delivery information is one click from the footer')
    await page.keyboard.press('Escape')
    await page.goto(BASE + '/terms')
    await page.getByRole('heading', { name: 'Публічна оферта', level: 1 }).waitFor()
    check((await page.locator('.blog-prose').textContent()).includes('Продавець — ФОП Продавець') && await page.getByRole('heading', { name: '1. Загальні положення' }).count() === 1, 'documents: /terms shows the text from the dashboard')
    await page.goto(BASE + '/')
    await page.locator('.product-card').first().waitFor()
    await page.keyboard.press('Escape')
    await page.screenshot({ path: `${output}/website-stage5-home-1280.png`, fullPage: true })
    check(errors.length === 0, 'home: no runtime errors ' + errors.join('; '))
    await context.close()
  }
  // -------------------------------------------------- phone: footer targets
  {
    const { page, context } = await open({}, { width: 360, height: 800 })
    await page.goto(BASE + '/')
    await page.locator('.product-card').first().waitFor()
    const small = await page.locator('.footer-links a, .footer-links button').evaluateAll((nodes) => nodes.filter((n) => n.getBoundingClientRect().height < 44).length)
    check(small === 0, 'W-26: footer links are 44 px tall on phones')
    await context.close()
  }
  // ------------------------------------------------------ offline: W-27
  {
    const { page, context } = await open({ offline: true })
    await page.goto(BASE + '/')
    const alert = page.locator('.state-block.state-error')
    await alert.waitFor()
    check(await alert.getAttribute('role') === 'alert' && (await alert.textContent()).includes('Немає зв’язку з магазином'), 'W-27: a network failure says so, as an alert, with a retry')
    check(await alert.getByRole('button', { name: 'Спробувати ще раз' }).count() === 1, 'W-27: error state offers a retry')
    await context.close()
  }
  // ------------------------------------------------------------- profile
  for (const width of [320, 1280]) {
    const { page, context, errors } = await open({ signedIn: true }, { width, height: 900 })
    await page.goto(BASE + '/profile')
    await page.locator('.order-record').first().waitFor()
    if (width === 1280) {
      const cards = await page.locator('.profile-card .profile-card-head').allTextContents()
      // Header: signed-in mark and sign-out next to the cart; profile page layout.
      const actions = await page.locator('.header-actions > button').evaluateAll((nodes) => nodes.filter((n) => getComputedStyle(n).display !== 'none').map((n) => n.getAttribute('aria-label')))
      check(actions.indexOf('Вийти з профілю') === actions.findIndex((label) => label.startsWith('Кошик')) + 1, `header: sign-out sits right after the cart (${actions.join(' | ')})`)
      const exit = page.locator('.logout-btn'), cart = page.locator('.cart-button')
      const [eb, cb] = [await exit.boundingBox(), await cart.boundingBox()]
      check(eb.width === cb.width && eb.height === cb.height && Math.abs(eb.y - cb.y) < 1, 'header: sign-out has the same size and line as the cart button')
      check(await page.locator('.icon-btn.signed-in').count() === 1, 'header: profile icon shows that you are signed in')
      const main = await page.locator('.profile-main').boundingBox(), aside = await page.locator('.profile-cards').boundingBox()
      check(main.x < aside.x && Math.abs(main.y - aside.y) < 2, 'profile: orders and settings sit side by side on desktop')
      check((await page.locator('.profile-greeting').textContent()).startsWith('Вітаємо, Олена!') && await page.locator('.profile-hero dl.profile-facts dd').count() === 2, 'profile: greeting and key numbers on top')
      check(cards.length === 3 && cards[0].startsWith('Мій обліковий запис') && cards[1].includes('Потрібне підтвердження') && cards[2].includes('Не підключено'), 'W-22: three cards, each with its state in words')
      check((await page.locator('.profile-card').nth(2).textContent()).includes('Вхід через Google і зв’язування — різні речі'), 'W-22: sign-in and linking are explained as different things')
      const shipped = page.locator('.order-record').nth(0)
      check(await shipped.locator('[aria-current="step"]').textContent() === 'Відправлено', 'W-23: the current stage is marked for assistive technology')
      check(await shipped.locator('.order-steps li.done').count() === 2, 'W-23: earlier stages are shown as done')
      check(await shipped.getByRole('link', { name: 'Відстежити на сайті Нової пошти' }).getAttribute('href') === 'https://novaposhta.ua/tracking/?cargo_number=20451234567890', 'W-23: tracking link for a real waybill number')
      check(await shipped.getByRole('button', { name: 'Скопіювати ТТН 20451234567890' }).count() === 1, 'W-23: waybill can be copied')
      const crm = page.locator('.order-record').nth(1)
      check(await crm.locator('.order-steps').count() === 0 && (await crm.textContent()).includes('Очікує дзвінка'), 'W-23: a CRM status is shown as is, not forced into stages')
      check(await crm.getByRole('link', { name: /Відстежити/ }).count() === 0, 'W-23: no tracking link for an unknown number format')
      check((await page.locator('.order-record').nth(2).locator('.status-chip').textContent()) === 'Скасовано', 'W-23: cancelled order is a clear state')
      check(await crm.locator('details.order-details').count() === 1 && await crm.locator('.order-cancel button').count() === 1, 'W-23: details are folded; cancel sits apart from tracking')
    }
    const cdp = await context.newCDPSession(page)
    await auditPage(page, cdp, `${width}px signed-in profile`, check, { errors })
    await auditText(page, `${width}px signed-in profile`, check)
    await page.screenshot({ path: `${output}/website-stage5-profile-${width}.png`, fullPage: true })
    if (width === 1280) {
      await page.locator('.logout-btn').click()
      await page.locator('.profile-page.is-guest').waitFor()
      check(await page.locator('.logout-btn').count() === 0 && (await page.locator('.notice').textContent()).includes('Ви вийшли з профілю'), 'header: sign-out works and says so; the button disappears')
    }
    await context.close()
  }
  // ------------------------------------------------------------- article
  for (const width of [360, 1280]) {
    const { page, context, errors } = await open({ signedIn: true }, { width, height: 900 })
    await page.goto(BASE + '/blog/note')
    await page.locator('.blog-prose').waitFor()
    await page.locator('.own-comment').first().waitFor()
    if (width === 1280) {
      const measure = await page.locator('.blog-prose p').first().evaluate((el) => ({ size: parseFloat(getComputedStyle(el).fontSize), width: el.getBoundingClientRect().width, line: parseFloat(getComputedStyle(el).lineHeight) / parseFloat(getComputedStyle(el).fontSize) }))
      check(measure.size >= 17 && measure.width <= 760 && measure.line >= 1.6, `W-24: readable measure (${measure.size}px, ${Math.round(measure.width)}px wide, line ${measure.line.toFixed(2)})`)
      const chips = await page.locator('.own-comment .status-chip').allTextContents()
      check(chips[0].startsWith('На модерації') && chips[1].startsWith('Не схвалено'), 'W-25: own comment states are words in chips')
      await page.getByRole('button', { name: 'Відповісти' }).first().click()
      check((await page.locator('.reply-target').textContent()).includes('Відповідаєте: Ігор'), 'W-25: reply shows whom you answer')
      await page.locator('.reply-target').getByRole('button', { name: 'Скасувати відповідь' }).click()
      check(await page.locator('.reply-target').count() === 0, 'W-25: reply can be cancelled where it is announced')
    }
    const cdp = await context.newCDPSession(page)
    await auditPage(page, cdp, `${width}px article`, check, { errors })
    await auditText(page, `${width}px article`, check)
    await context.close()
  }
} finally { await browser.close() }
console.log(`WEBSITE STAGE 5: ${checks - failures.length}/${checks}`)
if (failures.length) process.exitCode = 1
