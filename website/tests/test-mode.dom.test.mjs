// Test mode on the storefront: the banner and a separate browser cart.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync, readdirSync} from 'node:fs'
import {JSDOM, VirtualConsole} from 'jsdom'

const assets = new URL('../dist/assets/', import.meta.url)
const bundle = readFileSync(new URL(readdirSync(assets).find(name => /^index-.*\.js$/.test(name)), assets), 'utf8')
const response = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'content-type': 'application/json'}})
const sandbox = data => new Response(JSON.stringify(data), {headers: {'content-type': 'application/json', 'x-accord-test-mode': '1'}})
async function waitFor(check) {
  const until = Date.now() + 4000
  while (Date.now() < until) {if (check()) return; await new Promise(resolve => setTimeout(resolve, 15))}
  assert.ok(check(), 'state did not become ready')
}
function mount({marker, active}) {
  const virtualConsole = new VirtualConsole()  // jsdom cannot reload; the attempt is recorded below
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {url: 'https://accordniche.pp.ua/', runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole})
  const window = dom.window, asked = []
  window.scrollTo = () => {}
  if (marker) window.document.cookie = 'accord_test_view=1; Path=/'
  window.localStorage.setItem('accord:niche:cart', JSON.stringify({901: 1}))
  window.localStorage.setItem('accord:niche:cart:test', JSON.stringify({3: 2}))
  window.fetch = async input => {
    const url = new URL(input, window.location.href)
    if (url.pathname === '/api/public/test-mode/status') return response(active ? {active: true, expires_at: '2026-11-26T20:00:00Z'} : {active: false, expires_at: null})
    if (url.pathname === '/api/public/products') {asked.push(url.searchParams.get('ids')); return active ? sandbox([]) : response([])}
    if (url.pathname === '/api/web/session') return response({account: {signed_in: false, has_session: false}, csrf: 'a'.repeat(48)})
    if (url.pathname === '/api/public/storefront') return response({hits: [], recommended: [], new_arrivals: [], selection: [], total: 0, available: 0, window_days: 90})
    return response({}, 404)
  }
  window.eval(bundle)
  return {window, asked}
}

test('while test mode is on, the site shows the banner and uses its own cart', async () => {
  const {window, asked} = mount({marker: true, active: true})
  try {
    await waitFor(() => window.document.querySelector('.test-mode-banner'))
    assert.match(window.document.querySelector('.test-mode-banner').textContent, /ТЕСТ-РЕЖИМ/)
    assert.equal(window.document.querySelector('.test-mode-banner a'), null, 'no exit link: test mode is site-wide')
    await waitFor(() => asked.length)
    assert.deepEqual(asked, ['3'], 'sandbox ids from the test cart, the live cart is untouched')
    assert.equal(window.localStorage.getItem('accord:niche:cart'), '{"901":1}')
  } finally {window.close()}
})

test('a visitor without test mode sees the live cart and no banner', async () => {
  const {window, asked} = mount({marker: false, active: false})
  try {
    await waitFor(() => asked.length)
    assert.deepEqual(asked, ['901'])
    assert.equal(window.document.querySelector('.test-mode-banner'), null)
    assert.equal(window.sessionStorage.getItem('accord:test-mode:reloaded:on'), null, 'no reload for ordinary visitors')
    assert.equal(window.sessionStorage.getItem('accord:test-mode:reloaded:off'), null)
  } finally {window.close()}
})

test('test mode turned off in the panel: the test cart and marker are dropped once', async () => {
  const {window} = mount({marker: true, active: false})
  try {
    await waitFor(() => window.sessionStorage.getItem('accord:test-mode:reloaded:off') === '1')
    assert.ok(['{}', null].includes(window.localStorage.getItem('accord:niche:cart:test')), 'no sandbox ids survive')
    assert.doesNotMatch(window.document.cookie, /accord_test_view=1/)
    assert.equal(window.localStorage.getItem('accord:niche:cart'), '{"901":1}')
  } finally {window.close()}
})

test('test mode switched on: a visitor with the live cart reloads once into the test cart', async () => {
  const {window} = mount({marker: false, active: true})
  try {
    await waitFor(() => window.sessionStorage.getItem('accord:test-mode:reloaded:on') === '1')
    assert.equal(window.localStorage.getItem('accord:niche:cart'), '{"901":1}', 'the live cart is kept for later')
  } finally {window.close()}
})
