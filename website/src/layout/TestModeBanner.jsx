import { useEffect } from 'react'
import { useStoreRequest } from '../useStoreRequest'

// The server sets accord_test_view=1 next to the signed test-mode cookie. It
// only chooses the browser cart: sandbox goods have their own ids (1–30), so a
// shared cart would show live products with the same ids after leaving.
export const TEST_VIEW = typeof document !== 'undefined' && /(?:^|;\s*)accord_test_view=1(?:;|$)/.test(document.cookie)
export const CART_KEY = TEST_VIEW ? 'accord:niche:cart:test' : 'accord:niche:cart'

// Shown only in the system administrator's test-mode browser: the shop data
// on screen is a sandbox, and checkout and sign-in are switched off.
// At most one automatic reload per tab, so a missing marker can never loop.
function reloadOnce() {
  try {
    if (sessionStorage.getItem('accord:test-mode:reloaded')) return
    sessionStorage.setItem('accord:test-mode:reloaded', '1')
  } catch {return}
  location.reload()
}

export function TestModeBanner() {
  const request = useStoreRequest('/api/public/test-mode/status')
  const active = Boolean(request.data?.active)
  useEffect(() => {
    // Turned off in the panel or expired while the marker is still here:
    // drop the test cart and the marker, then show the live shop.
    if (!request.data || active || !TEST_VIEW) return
    try {localStorage.removeItem('accord:niche:cart:test')} catch {}
    document.cookie = 'accord_test_view=; Max-Age=0; Path=/; Secure; SameSite=Lax'
    reloadOnce()
  }, [request.data, active])
  useEffect(() => {
    // Entered test mode in a tab that started with the live cart: reload once
    // so the cart switches to the test one.
    if (active && !TEST_VIEW) reloadOnce()
  }, [active])
  if (!active) return null
  const until = new Intl.DateTimeFormat('uk-UA', {timeStyle: 'short'}).format(new Date(request.data.expires_at))
  return <div className="test-mode-banner" role="status"><span><b>ТЕСТ-РЕЖИМ</b> · тестові аромати й статті, оформлення замовлень вимкнено · до {until}</span><a href="/api/public/test-mode/exit">Вийти</a></div>
}
