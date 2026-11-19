// W-33: performance budgets for the built storefront. The limits are the
// measured baseline of v1.41.0 plus ~10 % headroom (JS 113.0 kB, CSS 10.5 kB
// gzip): a change that grows the first download noticeably must say why and
// move the budget on purpose. Layout stability (CLS) is measured in the real
// browser by qa/browser-website-motion.mjs.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync, readdirSync} from 'node:fs'
import {gzipSync} from 'node:zlib'

const assets = new URL('../dist/assets/', import.meta.url)
const files = readdirSync(assets)
const gzip = name => gzipSync(readFileSync(new URL(name, assets))).length
const BUDGET = {js: 125 * 1024, css: 12 * 1024}

test('first view downloads one script and one stylesheet', () => {
  const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
  assert.equal((html.match(/<script[^>]+src=/g) || []).length, 1, 'one entry script')
  assert.equal((html.match(/<link[^>]+rel="stylesheet"/g) || []).length, 1, 'one stylesheet')
  assert.doesNotMatch(html, /<link[^>]+rel="preload"[^>]+as="image"/, 'no image preload without a measured LCP reason')
})

test('JavaScript stays within the gzip budget', () => {
  const total = files.filter(name => name.endsWith('.js')).reduce((sum, name) => sum + gzip(name), 0)
  assert.ok(total <= BUDGET.js, `JS ${(total / 1024).toFixed(1)} kB > ${BUDGET.js / 1024} kB`)
})

test('CSS stays within the gzip budget', () => {
  const total = files.filter(name => name.endsWith('.css')).reduce((sum, name) => sum + gzip(name), 0)
  assert.ok(total <= BUDGET.css, `CSS ${(total / 1024).toFixed(1)} kB > ${BUDGET.css / 1024} kB`)
})
