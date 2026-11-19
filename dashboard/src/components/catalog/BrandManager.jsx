import { useMemo, useState } from 'react'
import { api } from '../../api'
import { ErrorBar, Field, Modal, useToast } from '../ui'

// Бренди замість категорій. Перейменування бренду оновлює назву в усіх його
// товарах; прихований бренд ховає свої товари з вітрини, не змінюючи їхнього
// власного прапорця; видалити можна лише бренд без товарів.
function BrandForm({ brand, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', description: '', sort_order: 0, is_active: true, ...brand })
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const set = (key) => (event) => setForm((old) => ({ ...old, [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }))
  const save = async (event) => {
    event.preventDefault(); if (busy) return
    setBusy(true); setError('')
    const payload = { name: form.name.trim(), description: form.description || null, sort_order: Number(form.sort_order) || 0, is_active: form.is_active }
    try { await (brand?.id ? api.brands.update(brand.id, payload) : api.brands.create(payload)); await onSaved(); onClose() }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <Modal title={brand?.id ? `Бренд «${brand.name}»` : 'Новий бренд'} onClose={() => !busy && onClose()}
    footer={<><button className="btn ghost" onClick={onClose} disabled={busy}>Скасувати</button><button className="btn" type="submit" form="catalog-brand-form" disabled={busy || !form.name.trim()}>Зберегти</button></>}>
    <form id="catalog-brand-form" onSubmit={save} className="stack">
      <ErrorBar error={error} />
      <Field label="Назва бренду" hint={brand?.id ? `Нова назва з’явиться в усіх ${brand.products_count} товарах бренду` : 'Як на флаконі: Creed, Maison Francis Kurkdjian'}>
        <input className="input" aria-label="Назва бренду" maxLength={100} required autoFocus value={form.name} onChange={set('name')} />
      </Field>
      <Field label="Опис" hint="Необовʼязково: коротко про парфумерний дім"><textarea className="input" aria-label="Опис бренду" maxLength={2000} value={form.description || ''} onChange={set('description')} /></Field>
      <Field label="Порядок" hint="Менше число — вище в списку брендів. Однакові йдуть за алфавітом"><input className="input" aria-label="Порядок бренду" type="number" value={form.sort_order} onChange={set('sort_order')} /></Field>
      <label className="catalog-check"><input type="checkbox" checked={form.is_active} onChange={set('is_active')} />Показувати бренд і його товари на вітрині</label>
    </form>
  </Modal>
}

export default function BrandManager({ brands, onClose, onChanged }) {
  const [editing, setEditing] = useState(null), [busy, setBusy] = useState(0), [query, setQuery] = useState('')
  const notify = useToast()
  const shown = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('uk-UA')
    return needle ? brands.filter((b) => b.name.toLocaleLowerCase('uk-UA').includes(needle)) : brands
  }, [brands, query])
  const toggle = async (brand) => {
    setBusy(brand.id)
    try { await api.brands.update(brand.id, { is_active: !brand.is_active }); await onChanged(); notify(brand.is_active ? `«${brand.name}» приховано` : `«${brand.name}» знову на вітрині`) }
    catch (err) { notify(err.message, 'bad') } finally { setBusy(0) }
  }
  const remove = async (brand) => {
    if (!confirm(`Видалити бренд «${brand.name}»? Товарів у нього немає.`)) return
    setBusy(brand.id)
    try { await api.brands.remove(brand.id); await onChanged(); notify('Бренд видалено') }
    catch (err) { notify(err.message, 'bad') } finally { setBusy(0) }
  }
  return <><Modal title="Бренди" onClose={onClose} footer={<button className="btn ghost" onClick={onClose}>Закрити</button>}>
    <div className="taxonomy-manager">
      <p className="muted">Бренд — це група товарів у каталозі, фільтрах сайту, Mini App, боті та промокодах. Кожен об’єм аромату — окремий товар того самого бренду.</p>
      <div className="catalog-block-head">
        <input className="input" type="search" aria-label="Знайти бренд" placeholder="Знайти бренд…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <button className="btn small" onClick={() => setEditing({})}>Новий бренд</button>
      </div>
      {!brands.length && <p className="muted">Брендів поки немає. Додайте перший — і обирайте його в картці товару.</p>}
      <div className="taxonomy-list">{shown.map((brand) => <article className="taxonomy-row" key={brand.id}>
        <div><strong>{brand.name}</strong><div className="muted">{brand.products_count} товарів · {brand.is_active ? 'на вітрині' : 'прихований'}</div></div>
        <div className="row">
          <button className="btn ghost small" onClick={() => setEditing(brand)}>Змінити</button>
          <button className="btn ghost small" disabled={busy === brand.id} onClick={() => toggle(brand)}>{brand.is_active ? 'Приховати' : 'Показати'}</button>
          {brand.products_count === 0 && <button className="btn danger small" disabled={busy === brand.id} onClick={() => remove(brand)}>Видалити</button>}
        </div>
      </article>)}</div>
    </div>
  </Modal>{editing && <BrandForm brand={editing.id ? editing : null} onClose={() => setEditing(null)} onSaved={onChanged} />}</>
}
