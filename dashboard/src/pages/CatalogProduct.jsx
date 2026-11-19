import {publicationState} from '../commerce'
import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { api, isAdmin } from '../api'
import { useProductImage } from '../components/catalog/useProductImage'
import { ErrorBar, Field, Info, Loading, money, useToast } from '../components/ui'
import { BrandFields, DescriptionField, DisplayFields, PriceFields, ProductImageField, PerfumeFields, perfumePayload, changeField, brandPayload, pricePayload } from '../components/catalog/ProductFields'
import { PageHeader } from '../components/page'
import { StateBadge } from '../components/StateBadge'

function EditBlock({ title, product, fields, payload, onSaved, children }) {
  const [editing, setEditing] = useState(false), [form, setForm] = useState(product)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const notify = useToast()
  const start = () => { setForm({ ...product }); setError(''); setEditing(true) }
  const save = async (event) => {
    event.preventDefault(); if (busy) return
    setBusy(true); setError('')
    try {
      const changes = payload(form)
      const updated = await api.products.patch(product.id, changes)
      const keys = new Set(Object.keys(changes))
      if (keys.has('brand_id')) keys.add('brand')
      if (keys.has('photo_url')) keys.add('has_photo')
      // A slower response from another block must not restore its older snapshot.
      onSaved((current) => current?.id === updated.id ? { ...current, ...Object.fromEntries([...keys].map((key) => [key, updated[key]])) } : current)
      setEditing(false); notify(`${title}: збережено`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <section className="catalog-edit-block" aria-label={title}><div className="catalog-block-head"><h2>{title}</h2>{!editing && isAdmin() && <button className="btn ghost small" onClick={start}>Редагувати</button>}</div>{editing ? <form onSubmit={save}><ErrorBar error={error} /><fieldset disabled={busy}>{fields(form, setForm)}</fieldset><div className="catalog-block-actions"><button className="btn ghost" type="button" disabled={busy} onClick={() => setEditing(false)}>Скасувати</button><button className="btn" disabled={busy}>{busy ? 'Зберігаємо…' : 'Зберегти блок'}</button></div></form> : children}</section>
}
function CurrentImage({ product }) {
  const [image, error] = useProductImage(product)
  return <div className="catalog-detail-image">{image ? <img src={image} alt={product.name} /> : <span className="muted">{error || (product.has_photo ? 'Завантажуємо зображення…' : 'Зображення не додано')}</span>}</div>
}

export default function CatalogProduct() {
  const { id } = useParams(), location = useLocation()
  const [product, setProduct] = useState(null), [brands, setBrands] = useState([])
  const [error, setError] = useState(''), [retry, setRetry] = useState(0)
  useEffect(() => {
    let alive = true; setError(''); setProduct(null)
    Promise.all([api.products.get(id), api.brands.list()]).then(([p, b]) => { if (alive) { setProduct(p); setBrands(b) } }).catch((err) => alive && setError(err.message))
    return () => { alive = false }
  }, [id, retry])
  const back = location.state?.catalogBack || '/catalog'
  if (error) return <><Link className="btn ghost" to={back}>← Каталог</Link><ErrorBar error={error} /><button className="btn" onClick={() => setRetry((n) => n + 1)}>Повторити</button></>
  if (!product) return <Loading />
  const props = { product, onSaved: setProduct }
  const publication=publicationState(product)
  return <div className="catalog-product-page">
    <Link className="btn ghost catalog-back-link" to={back}>← До каталогу</Link>
    <PageHeader title={product.name} description="Єдині дані для сайту, Mini App і бота." actions={<StateBadge tone={publication.buyable?'success':'neutral'}>{publication.label}</StateBadge>}/>
    <section className="card commerce-publication"><div><h2>Стан на вітрині</h2><p>{!product.is_active?'Товар приховано.':Number(product.price)<=0?'Активний товар без ціни не публікується на сайті.':publication.buyable?'Покупець може вибрати цей варіант і додати його в кошик.':'Товар можна переглянути, але оформлення недоступне без залишку.'}</p><small className="faint">{!product.photo_url && !product.has_photo?'Зображення не додано. ':''}{!product.description?'Опис не додано.':''}</small></div>{publication.visible && <a className="btn ghost small" href={'https://accordniche.pp.ua/aroma/'+product.id} target="_blank" rel="noopener noreferrer">Переглянути на сайті ↗</a>}</section>
    <div className="catalog-sku-panel"><Info label="Артикул (SKU)" copy={product.sku}><strong className="mono">{product.sku}</strong></Info><span className="muted">Автоматично створений · незмінний</span></div>
    <div className="catalog-detail-grid">
      <EditBlock {...props} title="Основне та відображення" payload={(f) => ({ name: f.name.trim(), stock: Number(f.stock), sort_order: Number(f.sort_order), is_active: f.is_active, is_new: f.is_new })} fields={(f, set) => <><Field label="Назва товару"><input className="input" aria-label="Назва товару" required maxLength={255} value={f.name} onChange={changeField(set, 'name')} /></Field><DisplayFields form={f} setForm={set} /></>}><p>{product.is_new ? 'Новинка · показується в розділі «Новинки»' : 'Звичайний товар'}</p><p>Залишок: <strong>{product.stock} шт.</strong> · Порядок: {product.sort_order}</p></EditBlock>
      <EditBlock {...props} title="Бренд" payload={brandPayload} fields={(f, set) => <BrandFields form={f} setForm={set} brands={brands} />}><p><strong>{product.brand || 'Бренд не обрано'}</strong></p>{!product.brand_id && <p className="muted">Без бренду аромат не з’явиться у фільтрі брендів на сайті й у боті.</p>}{product.brand_id && brands.find((b) => b.id === product.brand_id)?.is_active === false && <p className="muted">Бренд приховано — товар не видно на вітрині.</p>}</EditBlock>
      <EditBlock {...props} title="Парфумерія" payload={perfumePayload} fields={(f, set) => <PerfumeFields form={f} setForm={set} />}><p>{product.volume_ml ? `${product.volume_ml} мл` : "Обʼєм не задано"} · {{male:"чоловічий",female:"жіночий",unisex:"унісекс"}[product.gender] || "унісекс"}{product.is_featured ? " · рекомендація магазину" : ""}</p></EditBlock>
      <EditBlock {...props} title="Ціни та акція" payload={pricePayload} fields={(f, set) => <PriceFields form={f} setForm={set} />}><p className="catalog-detail-price">{money(product.price)} {product.is_sale && <s>{money(product.old_price)}</s>}</p><p>{product.is_sale ? 'Акція · знижка відображається в каталозі' : 'Акція вимкнена'}</p></EditBlock>
      <EditBlock {...props} title="Зображення" payload={(f) => ({ photo_url: f.photo_url || null })} fields={(f, set) => <><ProductImageField form={f} setForm={set} />{product.has_photo && !f.photo_url && <p className="muted">Збереження порожнього зображення прибере поточне фото.</p>}</>}><CurrentImage product={product} /></EditBlock>
      <div className="catalog-description-block"><EditBlock {...props} title="Опис" payload={(f) => ({ description: f.description || null })} fields={(f, set) => <DescriptionField form={f} setForm={set} />}><p className="catalog-detail-description">{product.description || 'Опис не додано'}</p></EditBlock></div>
    </div>
  </div>
}
