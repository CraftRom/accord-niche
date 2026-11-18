// W-01 / W-02 / W-14: readable text on the light storefront.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const read = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
const tokens = read('tokens.css')
const css = ['styles.css', 'interface.css', 'motion.css'].map(read).join('\n')
const hex = h => { h = h.replace('#', ''); if (h.length === 3) h = [...h].map(c => c + c).join(''); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)) }
const lum = rgb => rgb.map(v => v / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4).reduce((s, c, i) => s + c * [.2126, .7152, .0722][i], 0)
const ratio = (a, b) => { const x = lum(hex(a)), y = lum(hex(b)); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) }
const token = name => tokens.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))[1]

test('every text token passes AA on every light surface', () => {
  const surfaces = ['surface', 'surface-warm', 'surface-soft'].map(token)
  for (const name of ['text-primary', 'text-secondary', 'text-subtle', 'text-accent', 'text-danger'])
    for (const surface of surfaces) assert.ok(ratio(token(name), surface) >= 4.5, `${name} on ${surface}: ${ratio(token(name), surface).toFixed(2)}`)
})

test('no light-surface rule paints text below 4.5:1 on white', () => {
  // Rules on the black footer, the dark «how it works» band, black buttons and
  // the decorative hero lettering legitimately use light text.
  const darkContext = /footer|how-section|steps|step-number|inverse|section-heading\.light|btn\.primary|hit-badge|hero-lettering/
  const offenders = []
  for (const [, selector, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (darkContext.test(selector)) continue
    for (const [, colour] of body.matchAll(/(?<![-\w])color:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b/g))
      if (ratio(colour, '#ffffff') < 4.5) offenders.push(`${selector.trim().slice(-50)} ${colour}`)
  }
  assert.deepEqual(offenders, [])
})

test('functional text is at least 12px; buttons at least 13px', () => {
  const small = []
  for (const [, selector, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (/brandmark-bottom/.test(selector)) continue // decorative wordmark, marked data-decorative
    for (const [, size] of body.matchAll(/font-size:\s*([\d.]+)px/g)) if (Number(size) < 12) small.push(`${selector.trim().slice(-50)} ${size}px`)
  }
  assert.deepEqual(small, [])
  assert.match(tokens, /--font-control:\s*13px/)
  assert.match(css, /\.btn\{[^}]*font-size:var\(--font-control\)/)
})

test('keyboard focus is never removed without a visible replacement', () => {
  assert.match(css, /:focus-visible\{outline:2px solid var\(--focus\)/)
  assert.match(css, /\.search-strip input:focus-visible/)
  assert.ok(ratio(token('focus'), token('surface')) >= 3, 'focus ring is visible on white (WCAG 1.4.11)')
})
