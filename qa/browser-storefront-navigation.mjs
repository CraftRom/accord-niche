import { pageFixture } from './paged-fixture.mjs'
// Regression for the real React storefront; neutral demo fixtures and intercepted API.
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
const output = process.env.QA_OUTPUT_DIR || new URL('./output/', import.meta.url).pathname
mkdirSync(output, { recursive: true })
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH, args: ['--no-sandbox', '--disable-dev-shm-usage'] } : {}) })
let checks = 0
const failures = []
const check = (ok, label) => { checks++; console.log(`${ok ? 'PASS' : 'FAIL'} ${label}`); if (!ok) failures.push(label) }
try {
  for (const variant of [{ width: 320, scheme: 'dark' }, { width: 390, scheme: 'light' }, { width: 1280, scheme: 'dark' }]) {
    const label = `${variant.width}px ${variant.scheme}`
    const context = await browser.newContext({ viewport: { width: variant.width, height: 820 } })
    const p = await context.newPage(), errors = [], requests = []
    p.on('pageerror', error => errors.push(error.message))
    let brandFailure = false, delayedBrand = false, large = false
    // Brands replaced categories: one level, many brands, picked from a rail or a searchable list.
    const brands = [{ id: 1, name: 'Creed', products_count: 4 }, { id: 2, name: 'Kilian', products_count: 2 }, { id: 3, name: 'Порожній бренд', products_count: 0 }, { id: 4, name: 'Nasomatto', products_count: 1 }, ...Array.from({ length: 14 }, (_, i) => ({ id: i + 5, name: `Будинок ${i + 5}`, products_count: 0 }))]
    const photo = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" rx="20" fill="#63ad94"/><path d="M60 70h80v90H60Z M80 70V55h40v15" fill="none" stroke="#fff" stroke-width="7"/></svg>')
    const goods = [
      { id: 1, name: 'Звичайний подарунок', brand_id: 2, price: '40', stock: 2 },
      { id: 2, name: 'Нова сумка', brand_id: 1, is_new: true, price: '300', stock: 5 },
      { id: 3, name: 'Звичайні навушники', brand_id: 1, price: '500', stock: 4 },
      { id: 4, name: 'Акційна сумка', brand_id: 1, price: '250', old_price: '400', is_sale: true, stock: 2 },
      { id: 5, name: 'Сумка без залишку', brand_id: 1, price: '150', stock: 0 },
      { id: 6, name: 'Самостійний товар', brand_id: 4, price: '180', stock: 3 },
      { id: 7, name: 'Товар без бренду', price: '60', stock: 1 },
      { id: 8, name: 'Акційний набір', brand_id: 2, price: '150', old_price: '200', is_sale: true, stock: 4 },
    ].map(item => ({ brand_id: null, ...item, brand: '', sku: `ELF-${item.id}`, photo_url: photo }))
    await p.addInitScript(scheme => {
      window.Telegram = { WebApp: { initData: 'user=%7B%22id%22%3A123%7D&auth_date=1&hash=test', platform: 'tdesktop', colorScheme: scheme, initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {}, disableVerticalSwipes() {}, onEvent(name, callback) { (window.__qaEvents ||= {})[name] = callback }, offEvent() {}, BackButton: { show() {}, hide() {}, onClick(callback) { window.__qaBack = callback }, offClick() {} } } }
    }, variant.scheme)
    await p.route('https://telegram.org/**', route => route.fulfill({ body: '' }))
    await p.route('**/api/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname
      let data = []
      if (path.endsWith('/config')) data = { age_confirmed: true, shop_name: 'Магазин', currency: 'грн', bonus_enabled: false, referral_enabled: false }
      else if (path.endsWith('/cart')) data = { lines: [], subtotal: '0' }
      else if (path.endsWith('/profile')) data = { first_name: 'QA', bonus_balance: '0' }
      else if (path.endsWith('/brands')) {
        if (brandFailure) { await route.fulfill({ status: 503, json: { detail: 'Демопомилка брендів' } }); return }
        data = brands
      }
      else if (/\/products\/\d+$/.test(path)) data = goods.find(item => item.id === Number(path.split('/').pop()))
      else if (path.endsWith('/products')) {
        const query = Object.fromEntries(url.searchParams); requests.push(query)
        const bid = Number(query.brand_id), search = (query.search || '').toLowerCase()
        const source = large ? Array.from({ length: 503 }, (_, i) => ({ ...goods[6], id: i + 1000, name: `Великий каталог ${i}`, is_new: i === 502 })) : goods
        const rows = source.filter(item => (!bid || item.brand_id === bid) && (!search || item.name.toLowerCase().includes(search) || item.sku.toLowerCase().includes(search)))
        data = rows.slice(Number(query.offset || 0), Number(query.offset || 0) + Number(query.limit || 500))
        if (delayedBrand && bid === 1) await new Promise(resolve => setTimeout(resolve, 500))
      }
      await route.fulfill({ json: pageFixture(route, data) })
    })
    const titles = () => p.locator('.store-card-title').allTextContents()
    const waitCount = count => p.waitForFunction(n => document.querySelectorAll('.store-card').length === n, count)
    const root = name => p.getByRole('group', { name: 'Бренди', exact: true }).getByRole('button', { name, exact: true })
    const sort = value => p.getByRole('button', { name: /^Сортування:/ }).click().then(() => p.getByRole('dialog', { name: 'Сортування товарів' }).getByRole('button', { name: value, exact: true }).click())
    await p.goto((process.env.MINIAPP_URL || 'http://127.0.0.1:5174') + '/app/')
    await waitCount(8)
    check((await titles())[0] === 'Нова сумка', `${label}: new goods first, entire assortment visible`)
    check(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${label}: no page overflow`)
    await p.screenshot({ path: join(output, `navigation-${variant.width}-${variant.scheme}.png`) })
    check(!await p.getByRole('group', { name: 'Категорії', exact: true }).count() && !await p.getByText('Без категорії', { exact: true }).count(), `${label}: no categories left in the storefront`)
    check(await p.getByRole('group', { name: 'Наявність товарів' }).getByRole('button', { name: 'Усі', exact: true }).getAttribute('aria-pressed') === 'true', `${label}: availability explicitly defaults to all goods`)
    check((await root('Creed').textContent()).includes('4'), `${label}: brand card shows how many goods the brand has`)
    const palette = await p.evaluate(() => { const css = getComputedStyle(document.documentElement); return { accent: css.getPropertyValue('--accent').trim(), page: css.getPropertyValue('--tg-bg').trim() } })
    // ACCORD NICHE brand (miniapp/src/styles.css), not the former ELFAR violet.
    check(palette.accent.toLowerCase() === (variant.scheme === 'dark' ? '#d9c8ae' : '#111111') && palette.page.toLowerCase() === (variant.scheme === 'dark' ? '#0a0a0a' : '#ffffff'), `${label}: system palette matches the ACCORD brand`)
    await p.evaluate(() => { window.Telegram.WebApp.themeParams = { bg_color: '#ff0000', text_color: '#ff0000', secondary_bg_color: '#ff0000' }; window.__qaEvents.themeChanged?.() })
    check(await p.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--tg-bg').trim()) === palette.page, `${label}: custom Telegram colours cannot break brand text contrast`)
    if (variant.width >= 700) {
      await p.getByRole('button', { name: 'Наступні бренди' }).click()
      await p.waitForFunction(() => document.querySelector('.store-categories').scrollLeft > 0)
      await p.waitForFunction(() => !document.querySelector('[aria-label="Попередні бренди"]').disabled)
      check(await p.getByRole('button', { name: 'Попередні бренди' }).isEnabled(), `${label}: desktop brand arrows work`)
    }

    await sort('Спочатку акції')
    check((await titles()).slice(0, 2).join() === 'Акційна сумка,Акційний набір' && (await titles()).length === 8, `${label}: sales first, ordinary goods retained`)
    await root('Kilian').click(); await waitCount(2)
    check(requests.at(-1).brand_id === '2', `${label}: brand selection is sent as brand_id`)
    await sort('Спочатку новинки')
    check((await titles()).length === 2, `${label}: brand without new goods is not empty`)
    await root('Creed').click(); await waitCount(4)
    check((await p.getByRole('navigation', { name: 'Обраний бренд' }).textContent()).includes('Creed'), `${label}: chosen brand is visible`)
    await p.getByRole('textbox', { name: 'Пошук товарів' }).fill('неіснуючий товар')
    await p.getByRole('heading', { name: 'Нічого не знайшли' }).waitFor()
    check(await p.getByRole('button', { name: 'Прибрати фільтр пошуку' }).isVisible(), `${label}: search condition is visible and removable`)
    await p.getByRole('button', { name: 'Прибрати фільтр пошуку' }).click(); await waitCount(4)
    check(await root('Creed').getAttribute('aria-pressed') === 'true', `${label}: clearing the search preserves the brand`)
    await p.getByRole('button', { name: 'Скинути фільтри', exact: true }).click(); await waitCount(8)
    check(await root('Усі').getAttribute('aria-pressed') === 'true', `${label}: full reset clears the brand`)
    await p.getByRole('textbox', { name: 'Пошук товарів' }).fill('навушники'); await waitCount(1)
    check((await titles())[0] === 'Звичайні навушники', `${label}: ordinary search match visible in novelty order`)
    await p.getByRole('button', { name: 'Прибрати фільтр пошуку' }).click(); await waitCount(8)
    await p.getByRole('button', { name: 'В наявності', exact: true }).click()
    check((await titles()).length === 7, `${label}: stock is the only inventory filter`)
    await p.getByRole('button', { name: 'В наявності', exact: true }).click()
    check((await titles()).length === 7 && await p.getByRole('button', { name: 'В наявності', exact: true }).getAttribute('aria-pressed') === 'true', `${label}: selecting stock twice is idempotent`)
    await root('Creed').click(); await waitCount(3)
    await p.getByRole('group', { name: 'Наявність товарів' }).getByRole('button', { name: 'Усі', exact: true }).click(); await waitCount(4)
    check(await root('Creed').getAttribute('aria-pressed') === 'true', `${label}: availability all preserves the brand`)
    await root('Усі').click(); await waitCount(8)

    await p.getByRole('button', { name: 'Усі бренди', exact: true }).click()
    const picker = p.getByRole('dialog', { name: 'Усі бренди' })
    await picker.waitFor()
    check(await p.evaluate(() => document.body.style.overflow === 'hidden'), `${label}: brand list locks background`)
    await p.setViewportSize({ width: variant.width, height: 360 })
    await p.waitForFunction(() => document.querySelector('.category-sheet').clientHeight <= innerHeight - 24)
    check(await picker.evaluate(element => element.scrollHeight > element.clientHeight && element.clientHeight <= innerHeight - 24), `${label}: long brand list has bounded scroll`)
    await picker.getByRole('textbox', { name: 'Пошук брендів' }).fill('KIL')
    check(await picker.getByRole('button', { name: 'Kilian', exact: true }).count() === 1 && await picker.getByRole('button', { name: 'Creed', exact: true }).count() === 0, `${label}: brand search ignores letter case`)
    await picker.getByRole('button', { name: 'Kilian', exact: true }).click(); await waitCount(2)
    check(await root('Kilian').getAttribute('aria-pressed') === 'true' && !await picker.count(), `${label}: picking a brand selects it and closes the list`)
    await p.setViewportSize({ width: variant.width, height: 820 })
    await p.getByRole('button', { name: 'Усі бренди', exact: true }).click(); await picker.waitFor()
    await p.screenshot({ path: join(output, `brand-picker-${variant.width}-${variant.scheme}.png`) })
    await picker.getByRole('button', { name: 'Усі аромати', exact: true }).click(); await waitCount(8)
    await root('Порожній бренд').click()
    await p.getByRole('heading', { name: 'Нічого не знайшли' }).waitFor()
    check(await p.getByRole('button', { name: 'Скинути пошук і фільтри' }).isVisible(), `${label}: an empty brand always has reset`)
    await p.getByRole('button', { name: 'Скинути пошук і фільтри' }).click(); await waitCount(8)
    check((await titles()).includes('Товар без бренду'), `${label}: goods without a brand stay in the full assortment`)
    delayedBrand = true
    await root('Creed').click()
    await p.waitForFunction(() => document.querySelector('.product-grid[aria-busy="true"]'))
    await root('Kilian').click(); await waitCount(2)
    await p.waitForTimeout(650)
    check((await titles()).join() === 'Звичайний подарунок,Акційний набір', `${label}: late request cannot overwrite the current brand`)
    delayedBrand = false
    await root('Creed').click(); await waitCount(4)
    await p.locator('.store-card-title').first().click()
    await p.getByRole('button', { name: 'Назад до каталогу' }).waitFor()
    brands.splice(0, 1)
    await p.getByRole('button', { name: 'Назад до каталогу' }).click(); await waitCount(8)
    check(!requests.at(-1).brand_id, `${label}: a deleted or hidden saved brand cannot lock the catalog`)
    brandFailure = true
    await p.reload(); await p.getByRole('button', { name: 'Повторити завантаження брендів' }).waitFor()
    check(await p.getByRole('alert').filter({ hasText: 'Демопомилка брендів' }).isVisible(), `${label}: brand failure is actionable`)
    brandFailure = false
    await p.getByRole('button', { name: 'Повторити завантаження брендів' }).click(); await waitCount(8)
    large = true
    await p.reload(); await waitCount(503)
    check((await titles())[0] === 'Великий каталог 502' && requests.some(query => query.offset === '500'), `${label}: more than 500 goods loaded, final-page novelty first`)
    check(!errors.length, `${label}: no runtime errors: ${errors.join('; ')}`)
    await context.close()
  }
} finally { await browser.close() }
writeFileSync(join(output, 'storefront-navigation-results.json'), JSON.stringify({ checks, failures }, null, 2))
console.log(`STOREFRONT NAVIGATION: ${checks - failures.length}/${checks}`)
if (failures.length) process.exit(1)
