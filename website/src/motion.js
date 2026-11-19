// Motion helpers for the storefront. Everything here is progressive
// enhancement: without the browser feature, or with «reduce motion» set in
// the system, the page behaves exactly as it does without animation and no
// content is ever hidden.
import { flushSync } from 'react-dom'

export const prefersReducedMotion = () =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Runs a route change inside a View Transition so the old and new page
 * cross-fade (the header keeps its own name and stays still). Falls back to a
 * plain update where the API is missing or motion is reduced.
 */
export function withViewTransition(update) {
  const start = typeof document !== 'undefined' && document.startViewTransition
  if (!start || prefersReducedMotion()) { update(); return }
  try {
    document.startViewTransition(() => flushSync(update))
  } catch {
    update()
  }
}

// Blocks that rise into view while scrolling. Things already on screen when
// they appear are left alone, so nothing above the fold blinks.
const TARGETS = [
  '.section-row', '.product-card', '.how-section .steps > article', '.blog-card',
  '.detail-grid > *', '.commerce-panel', '.order-summary', '.featured .product-grid',
].join(',')
const STAGGER_MS = 70
const STAGGER_MAX = 5

/**
 * Starts the scroll reveal and returns a cleanup function. Elements get
 * `reveal-pending` (hidden by CSS only under prefers-reduced-motion:
 * no-preference) and `revealed` once they enter the viewport; both classes
 * are removed after the transition so hover effects keep their own timing.
 */
export function startReveal(root = typeof document !== 'undefined' ? document.body : null) {
  if (!root || typeof IntersectionObserver !== 'function' || prefersReducedMotion()) return () => {}
  const seen = new WeakSet()
  const settle = (element) => {
    element.classList.remove('reveal-pending', 'revealed')
    element.style.removeProperty('--reveal-delay')
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      const element = entry.target
      observer.unobserve(element)
      element.classList.add('revealed')
      const delay = parseFloat(element.style.getPropertyValue('--reveal-delay')) || 0
      // transitionend can be skipped (tab hidden, display change); the timer
      // makes sure the element always returns to its plain state.
      const done = () => settle(element)
      element.addEventListener('transitionend', done, { once: true })
      setTimeout(done, delay + 900)
    }
  }, { rootMargin: '0px 0px -6% 0px', threshold: 0.08 })
  const scan = () => {
    const viewport = window.innerHeight || 0
    for (const element of root.querySelectorAll(TARGETS)) {
      if (seen.has(element)) continue
      seen.add(element)
      if (element.getBoundingClientRect().top < viewport) continue
      const siblings = element.parentElement ? [...element.parentElement.children].filter((node) => node.matches(TARGETS)) : []
      const index = Math.min(Math.max(siblings.indexOf(element), 0), STAGGER_MAX)
      element.style.setProperty('--reveal-delay', `${(index % (STAGGER_MAX + 1)) * STAGGER_MS}ms`)
      element.classList.add('reveal-pending')
      observer.observe(element)
    }
  }
  let frame = 0
  const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; scan() }) }
  const mutations = typeof MutationObserver === 'function' ? new MutationObserver(schedule) : null
  mutations?.observe(root, { childList: true, subtree: true })
  scan()
  return () => {
    observer.disconnect()
    mutations?.disconnect()
    if (frame) cancelAnimationFrame(frame)
    for (const element of root.querySelectorAll('.reveal-pending')) settle(element)
  }
}
