import { useStoreRequest } from '../useStoreRequest'

// Shown only in the system administrator's test-mode browser: the shop data
// on screen is a sandbox, and checkout and sign-in are switched off.
export function TestModeBanner() {
  const request = useStoreRequest('/api/public/test-mode/status')
  if (!request.data?.active) return null
  const until = new Intl.DateTimeFormat('uk-UA', {timeStyle: 'short'}).format(new Date(request.data.expires_at))
  return <div className="test-mode-banner" role="status"><span><b>ТЕСТ-РЕЖИМ</b> · тестові аромати й статті, оформлення замовлень вимкнено · до {until}</span><a href="/api/public/test-mode/exit">Вийти</a></div>
}
