import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBar, useToast } from './ui'
import { StateBadge } from './StateBadge'

const time = (value) => value ? new Intl.DateTimeFormat('uk-UA', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : ''
const HOURS = [1, 2, 4, 8, 24]

// Test mode is only for the system administrator: a temporary sandbox copy of
// the website with test perfumes and posts. It lives in its own database and
// opens only in the browser that follows the signed link below.
export default function TestModeCard() {
  const notify = useToast()
  const [info, setInfo] = useState(null)
  const [hours, setHours] = useState(2)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { api.system.testMode().then(setInfo).catch((err) => setError(err.message)) }, [])
  async function run(action, message) {
    setBusy(true); setError('')
    try { setInfo(await action()); notify(message) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const enable = () => run(() => api.system.enableTestMode(Number(hours)), info?.active ? 'Тест-режим перезапущено з чистими даними' : 'Тест-режим увімкнено')
  const disable = () => window.confirm('Вимкнути тест-режим? Тестові дані буде видалено.') && run(() => api.system.disableTestMode(), 'Тест-режим вимкнено, тестові дані видалено')
  return <div className="card u-mb-5 test-mode-card" aria-label="Тест-режим">
    <div className="row-between"><h2 className="u-m-0">Тест-режим сайту</h2><StateBadge tone={info?.active ? 'warning' : 'neutral'}>{info?.active ? 'увімкнено до ' + time(info.expires_at) : 'вимкнено'}</StateBadge></div>
    <p className="faint">Тимчасова копія сайту для перевірки: 10 реальних нішевих ароматів (по три обʼєми, з нотами й ілюстраціями) і 3 статті блогу. Дані лежать в окремій тестовій базі, а не в базі магазину, і бачить їх лише браузер, відкритий за посиланням нижче. Покупці, пошуковики, бот, Mini App і ця панель працюють як завжди.</p>
    <ul className="faint test-mode-rules">
      <li>Оформлення замовлень, вхід, SMS і коментарі в тест-режимі вимкнено — жодних замовлень у CRM чи сповіщень у Telegram.</li>
      <li>Сторінки тест-режиму позначені <code>noindex</code> і <code>no-store</code>: не потраплять у пошук і кеш.</li>
      <li>Режим вимикається сам після обраного часу; тестова база при цьому видаляється.</li>
    </ul>
    <ErrorBar error={error} />
    {info && <div className="test-mode-actions">
      <label className="faint">Тривалість <select className="input" aria-label="Тривалість тест-режиму" value={hours} disabled={busy} onChange={(event) => setHours(event.target.value)}>{HOURS.map((h) => <option key={h} value={h}>{h} год</option>)}</select></label>
      <button className="btn small" disabled={busy} onClick={enable}>{info.active ? 'Перезапустити з чистими даними' : 'Увімкнути тест-режим'}</button>
      {info.active && <>
        <a className="btn small" href={info.enter_url} target="_blank" rel="noopener noreferrer">Відкрити сайт у тест-режимі ↗</a>
        <button className="btn ghost small danger" disabled={busy} onClick={disable}>Вимкнути</button>
      </>}
    </div>}
    {info?.active && <p className="faint test-mode-meta">Увімкнув {info.created_by} · {info.aromas} ароматів ({info.products} SKU), {info.posts} статті. Посилання працює лише до {time(info.expires_at)}; не пересилайте його — воно відкриває тестові дані будь-кому, хто його має. Вийти з тест-режиму в браузері — кнопка «Вийти» на банері сайту.</p>}
  </div>
}
