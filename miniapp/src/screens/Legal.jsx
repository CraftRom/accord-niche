import { useEffect, useState } from 'react'

import { api } from '../api'
import { DOCUMENTS, blocks, documentFor, inline } from '../legal'
import { APP_VERSION } from '../version'

function Inline({ text }) {
  return inline(text).map((part, i) => part.bold ? <strong key={i}>{part.text}</strong> : <span key={i}>{part.text}</span>)
}

/** Документ із панелі: заголовки, абзаци, списки. HTML не виконується. */
function Markdown({ body }) {
  return blocks(body).map((block, i) => {
    if (block.type === 'h') return <h3 key={i} className="legal-h">{block.text}</h3>
    if (block.type === 'ul') return <ul key={i} className="legal-ul">{block.items.map((item, j) => <li key={j}><Inline text={item} /></li>)}</ul>
    return <p key={i} className="legal-p">{block.lines.map((line, j) => <span key={j}>{j > 0 && <br />}<Inline text={line} /></span>)}</p>
  })
}

function Document({ docKey, onBack }) {
  const doc = documentFor(docKey)
  const [state, setState] = useState({ loading: true, data: null, error: '' })
  useEffect(() => {
    let active = true
    setState({ loading: true, data: null, error: '' })
    api.legal(doc.source)
      .then((data) => { if (active) setState({ loading: false, data, error: '' }) })
      .catch((err) => { if (active) setState({ loading: false, data: null, error: err.message }) })
    return () => { active = false }
  }, [doc.source])
  useEffect(() => {
    if (!doc.section || !state.data) return
    const heading = [...document.querySelectorAll('.legal-h')].find((node) => node.textContent.startsWith(doc.section.slice(3)))
    heading?.scrollIntoView({ block: 'start' })
  }, [doc.section, state.data])
  return (
    <div className="screen legal">
      <button className="back" onClick={onBack}>Документи</button>
      <h1 className="legal-title">{state.data?.title || doc.title}</h1>
      {state.loading && <p className="hint" role="status">Завантажуємо документ…</p>}
      {state.error && <div className="banner warn" role="alert">{state.error}</div>}
      {state.data && !state.data.seller_ready && (
        <div className="banner warn">
          Продавець ще не вказав усі реквізити. Перед покупкою уточніть їх у менеджера.
        </div>
      )}
      {state.data && <Markdown body={state.data.body} />}
      <p className="hint legal-contact">Питання щодо умов — менеджеру в чаті замовлення.</p>
    </div>
  )
}

export function Legal({ initial, onBack }) {
  const [open, setOpen] = useState(initial || null)
  if (open) return <Document docKey={open} onBack={() => setOpen(null)} />
  return (
    <>
      <div className="head">
        {onBack && <button className="back" onClick={onBack}>Назад</button>}
        <h1>Умови та документи</h1>
        <p>Публічна оферта, обробка даних, повернення та обмін</p>
      </div>
      <div className="screen legal-list">
        {DOCUMENTS.map((d) => (
          <button key={d.key} className="legal-row" onClick={() => setOpen(d.key)}>
            <span className="grow">{d.title}</span>
            <span className="hint">›</span>
          </button>
        ))}
      </div>
      <p className="hint legal-contact">
        Програмний код і дизайн застосунку охороняються Законом України «Про авторське право
        і суміжні права». Автор: Halytskyi Dmytro.
      </p>
      <Footer />
    </>
  )
}

/** Підвал вітрини. Версія тут своя — панель керування має власну. */
export function Footer({ onLegal }) {
  return (
    <div className="footer">
      {onLegal && (
        <button className="footer-link" onClick={onLegal}>
          Умови, оферта й повернення
        </button>
      )}
      <div className="hint num">
        Вітрина v{APP_VERSION}
      </div>
    </div>
  )
}
