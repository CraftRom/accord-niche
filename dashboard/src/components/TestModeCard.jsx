import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBar, useToast } from './ui'
import { StateBadge } from './StateBadge'

const time = (value) => value ? new Intl.DateTimeFormat('uk-UA', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : ''
const HOURS = [1, 2, 4, 8, 24]

// Only the system administrator turns it on. While it is on, the whole website
// shows test perfumes and posts from a separate database; the shop's own data
// is untouched and comes back when test mode ends.
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
  const enable = () => (info?.active || window.confirm('Увімкнути тест-режим для всіх відвідувачів сайту? Поки він діє, покупці бачать тестові товари й не можуть оформити замовлення.')) && run(() => api.system.enableTestMode(Number(hours)), info?.active ? 'Тест-режим перезапущено з чистими даними' : 'Тест-режим увімкнено')
  const disable = () => window.confirm('Вимкнути тест-режим? Тестові дані буде видалено.') && run(() => api.system.disableTestMode(), 'Тест-режим вимкнено, тестові дані видалено')
  return <div className="card u-mb-5 test-mode-card" aria-label="Тест-режим">
    <div className="row-between"><h2 className="u-m-0">Тест-режим сайту</h2><StateBadge tone={info?.active ? 'warning' : 'neutral'}>{info?.active ? 'увімкнено до ' + time(info.expires_at) : 'вимкнено'}</StateBadge></div>
    <p className="faint">Поки тест-режим увімкнено, <b>сайт accordniche.pp.ua для всіх відвідувачів</b> показує 10 реальних нішевих ароматів (по три обʼєми, з нотами й ілюстраціями) і 3 статті блогу. Посилань чи кодів не потрібно — просто відкрийте сайт. Дані лежать в окремій тестовій базі; справжні товари, статті й замовлення не змінюються і повертаються, щойно режим вимкнеться.</p>
    <ul className="faint test-mode-rules">
      <li>Оформлення замовлень, вхід, SMS і коментарі на сайті тимчасово вимкнено — жодних замовлень у CRM чи сповіщень у Telegram. Покупці бачать банер «ТЕСТ-РЕЖИМ».</li>
      <li>Пошукові системи й прев’ю в месенджерах бачать справжній сайт, тож тест не потрапить у пошук.</li>
      <li>Mini App, Telegram-бот і ця панель працюють зі справжніми даними.</li>
      <li>Режим вимикається сам після обраного часу; тестова база при цьому видаляється.</li>
    </ul>
    <ErrorBar error={error} />
    {info && <div className="test-mode-actions">
      <label className="faint">Тривалість <select className="input" aria-label="Тривалість тест-режиму" value={hours} disabled={busy} onChange={(event) => setHours(event.target.value)}>{HOURS.map((h) => <option key={h} value={h}>{h} год</option>)}</select></label>
      <button className="btn small" disabled={busy} onClick={enable}>{info.active ? 'Перезапустити з чистими даними' : 'Увімкнути тест-режим'}</button>
      {info.active && <>
        <a className="btn small" href={info.site_url} target="_blank" rel="noopener noreferrer">Відкрити сайт ↗</a>
        <button className="btn ghost small danger" disabled={busy} onClick={disable}>Вимкнути</button>
      </>}
    </div>}
    {info?.active && <p className="faint test-mode-meta">Увімкнув {info.created_by} · {info.aromas} ароматів ({info.products} SKU), {info.posts} статті · сайт повернеться до справжніх даних о {time(info.expires_at)} або одразу після «Вимкнути».</p>}
  </div>
}
