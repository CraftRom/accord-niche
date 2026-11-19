import { useEffect, useRef, useState } from 'react'

import { api } from '../api'
import { ErrorBar, Field, Loading, useToast } from '../components/ui'
import BlogContent from '../components/BlogContent'
import { PageHeader } from '../components/page'
import { StateBadge } from '../components/StateBadge'
import './blog.css'

// Public offer and privacy policy: pages of the site (/terms, /privacy) and of
// the Mini App. Same Markdown editor as the blog; seller requisites are filled
// in from «Налаштування → Реквізити продавця» when the page is shown.
const PLACEHOLDERS = [
  ['{{SELLER_NAME}}', 'назва або ПІБ продавця'], ['{{SELLER_CODE}}', 'РНОКПП / ЄДРПОУ'],
  ['{{SELLER_ADDRESS}}', 'адреса'], ['{{SELLER_EMAIL}}', 'email'], ['{{SELLER_PHONE}}', 'телефон'],
  ['{{SITE}}', 'адреса сайту'], ['{{UPDATED}}', 'дата редакції'],
]
const PUBLIC = { terms: '/terms', privacy: '/privacy' }
const date = (value) => value ? new Intl.DateTimeFormat('uk-UA', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : ''

function DocumentEditor({ doc, defaults, onSaved }) {
  const notify = useToast()
  const [body, setBody] = useState(doc.body)
  const [preview, setPreview] = useState('')
  const [mode, setMode] = useState('text')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const text = useRef(null)
  useEffect(() => { setBody(doc.body); setMode('text') }, [doc.key, doc.updated_at])
  const dirty = body !== doc.body

  useEffect(() => {
    if (!dirty) return
    const warn = (event) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const showPreview = async () => {
    setMode('preview'); setError('')
    try { setPreview((await api.legal.preview(doc.key, body)).body) } catch (err) { setError(err.message) }
  }
  const insert = (before, after = '') => {
    const node = text.current
    if (!node) return
    const start = node.selectionStart, end = node.selectionEnd
    const next = body.slice(0, start) + before + body.slice(start, end) + after + body.slice(end)
    setBody(next)
    requestAnimationFrame(() => { node.focus(); node.selectionStart = node.selectionEnd = start + before.length + (end - start) })
  }
  const save = async (value = body) => {
    setBusy(true); setError('')
    try {
      const saved = await api.legal.save(doc.key, value)
      onSaved(saved)
      notify(saved.is_default ? 'Повернуто початковий шаблон' : 'Документ збережено й опубліковано')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const reset = () => {
    if (!window.confirm('Повернути початковий шаблон? Ваш текст буде замінено.')) return
    save('')
  }

  return <section className="card legal-editor" aria-labelledby={'legal-' + doc.key}>
    <div className="row-between">
      <h2 id={'legal-' + doc.key} className="u-m-0">{doc.title}</h2>
      <StateBadge tone={doc.is_default ? 'neutral' : 'success'}>{doc.is_default ? 'Початковий шаблон' : 'Власна редакція'}</StateBadge>
    </div>
    <p className="faint">
      На сайті: <a href={PUBLIC[doc.key]} target="_blank" rel="noopener noreferrer">{PUBLIC[doc.key]}</a>
      {doc.updated_at && <> · змінено {date(doc.updated_at)}{doc.updated_by ? ` (${doc.updated_by})` : ''}</>}
    </p>
    <ErrorBar error={error} />
    <div className="blog-editor-toolbar">
      <button type="button" className={'btn' + (mode === 'text' ? ' primary' : '')} aria-pressed={mode === 'text'} onClick={() => setMode('text')}>Текст</button>
      <button type="button" className={'btn' + (mode === 'preview' ? ' primary' : '')} aria-pressed={mode === 'preview'} onClick={showPreview}>Як побачить покупець</button>
    </div>
    {mode === 'preview'
      ? <div className="blog-editor-preview"><h2>{doc.title}</h2><BlogContent body={preview} /></div>
      : <>
        <div className="blog-format-tools" aria-label="Форматування">
          <button type="button" onClick={() => insert('\n## ')}>Розділ</button>
          <button type="button" onClick={() => insert('**', '**')}>Жирний</button>
          <button type="button" onClick={() => insert('\n- ')}>Список</button>
          {PLACEHOLDERS.slice(0, 3).map(([token, label]) => <button type="button" key={token} title={'Вставити: ' + label} onClick={() => insert(token)}>{token}</button>)}
        </div>
        <Field label="Текст документа" hint="Markdown. Реквізити в {{…}} підставляються автоматично з «Реквізитів продавця». Порожній текст повертає початковий шаблон.">
          <textarea aria-label={'Текст: ' + doc.title} ref={text} className="input blog-source" maxLength={60000} rows={26} value={body} onChange={(event) => setBody(event.target.value)} />
        </Field>
        <p className="muted">{body.length} / 60000</p>
      </>}
    <div className="row">
      <button className="btn primary" type="button" disabled={!dirty || busy} onClick={() => save()}>{busy ? 'Збереження…' : 'Зберегти й опублікувати'}</button>
      <button className="btn ghost" type="button" disabled={!dirty || busy} onClick={() => setBody(doc.body)}>Скасувати зміни</button>
      <button className="btn ghost" type="button" disabled={busy || (doc.is_default && body === defaults)} onClick={reset}>Повернути шаблон</button>
    </div>
  </section>
}

export default function Documents() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [active, setActive] = useState('terms')
  useEffect(() => { api.legal.list().then(setData).catch((err) => setError(err.message)) }, [])
  if (error && !data) return <ErrorBar error={error} />
  if (!data) return <Loading />
  const doc = data.items.find((item) => item.key === active)
  const replace = (saved) => setData((old) => ({ ...old, items: old.items.map((item) => item.key === saved.key ? saved : item) }))
  return <>
    <PageHeader title="Документи" description="Публічна оферта й політика конфіденційності — сторінки сайту й Mini App" />
    <div className="card u-mb-5 legal-notice" role="note">
      <p className="u-m-0"><strong>Початкові шаблони складено з урахуванням законодавства України</strong> (ЦК України, закони «Про захист прав споживачів», «Про електронну комерцію», «Про захист персональних даних», постанова КМУ № 172). Це не юридична консультація: перед публікацією покажіть текст юристу й звірте з фактичними умовами магазину.</p>
      {!data.seller_ready && <p className="u-mb-0"><StateBadge tone="warning">Бракує реквізитів</StateBadge> Заповніть назву, адресу та email або телефон у «Налаштування → Реквізити продавця» — без них документ не ідентифікує продавця.</p>}
      <p className="faint u-mb-0">Підстановки: {PLACEHOLDERS.map(([token, label]) => <span key={token}><code>{token}</code> — {label}; </span>)}</p>
    </div>
    <nav className="settings-tabs u-mb-4" aria-label="Документи">
      {data.items.map((item) => <button type="button" key={item.key} className={`btn ghost small ${active === item.key ? 'active' : ''}`} aria-pressed={active === item.key} onClick={() => setActive(item.key)}>{item.title}</button>)}
    </nav>
    {doc && <DocumentEditor key={doc.key} doc={doc} defaults={data.defaults[doc.key]} onSaved={replace} />}
  </>
}
