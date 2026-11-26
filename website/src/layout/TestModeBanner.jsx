import { useEffect } from 'react'
import { useStoreRequest } from '../useStoreRequest'

// While test mode is on, the API sets accord_test_view=1. It only chooses the
// browser cart: test goods have their own ids (1–30), so a shared cart would
// show live products with the same ids once test mode ends.
export const TEST_VIEW = typeof document !== 'undefined' && /(?:^|;\s*)accord_test_view=1(?:;|$)/.test(document.cookie)
export const CART_KEY = TEST_VIEW ? 'accord:niche:cart:test' : 'accord:niche:cart'

// One automatic reload per direction per tab, so a missing marker never loops.
function reloadOnce(direction) {
  try {
    const key = 'accord:test-mode:reloaded:' + direction
    if (sessionStorage.getItem(key)) return
    sessionStorage.setItem(key, '1')
  } catch {return}
  location.reload()
}

// Shown to every visitor while the system administrator has test mode on.
export function TestModeBanner() {
  const request = useStoreRequest('/api/public/test-mode/status')
  const active = Boolean(request.data?.active)
  useEffect(() => {
    if (!request.data) return
    if (active && !TEST_VIEW) reloadOnce('on')  // switch to the test cart
    if (!active && TEST_VIEW) {                 // test mode ended: back to the live cart
      try {localStorage.removeItem('accord:niche:cart:test')} catch {}
      document.cookie = 'accord_test_view=; Max-Age=0; Path=/; Secure; SameSite=Lax'
      reloadOnce('off')
    }
  }, [request.data, active])
  if (!active) return null
  const until = new Intl.DateTimeFormat('uk-UA', {timeStyle: 'short'}).format(new Date(request.data.expires_at))
  return <div className="test-mode-banner" role="status"><span><b>ТЕСТ-РЕЖИМ</b> · на сайті тестові аромати й статті, оформлення замовлень тимчасово вимкнено · до {until}</span></div>
}
