import { Field } from '../ui'
import ImageField from '../ImageField'

export const emptyProduct = { brand: '', gender: 'unisex', volume_ml: '', is_featured: false, name: '', category_id: '', subcategory_id: '', description: '', photo_url: '', price: '', old_price: '', stock: 0, sort_order: 0, is_active: true, is_new: false, is_sale: false }
export const changeField = (setForm, key) => (event) => setForm((form) => ({ ...form, [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }))
export function groupPayload(form) { return { category_id: form.category_id ? Number(form.category_id) : null, subcategory_id: form.subcategory_id ? Number(form.subcategory_id) : null } }
export function pricePayload(form) { return { price: Number(form.price), old_price: form.old_price === '' || form.old_price == null ? null : Number(form.old_price), is_sale: Boolean(form.is_sale) } }
export function validateProduct(form) {
  if (!form.name?.trim()) return 'Вкажіть назву товару'
  if (form.volume_ml !== '' && form.volume_ml != null && (!Number.isInteger(Number(form.volume_ml)) || Number(form.volume_ml) < 1 || Number(form.volume_ml) > 1000)) return 'Обʼєм має бути цілим числом від 1 до 1000 мл'
  if (form.price === '' || !Number.isFinite(Number(form.price)) || Number(form.price) < 0) return 'Вкажіть невід’ємну ціну'
  if (form.is_sale && (!form.old_price || Number(form.old_price) <= Number(form.price))) return 'Для акції стара ціна має бути більшою за поточну'
  if (!Number.isInteger(Number(form.stock)) || Number(form.stock) < 0) return 'Залишок має бути цілим невід’ємним числом'
  return ''
}
export function TaxonomyFields({ form, setForm, categories, subcategories }) {
  const available = subcategories.filter((s) => !form.category_id || !s.category_id || Number(s.category_id) === Number(form.category_id))
  const changeCategory = (event) => {
    const category_id = event.target.value
    const current = subcategories.find((s) => s.id === Number(form.subcategory_id))
    setForm((old) => ({ ...old, category_id, subcategory_id: category_id && current?.category_id && current.category_id !== Number(category_id) ? '' : old.subcategory_id }))
  }
  return <div className="grid k2">
    <Field label="Категорія" hint="Можна залишити порожньою"><select className="input" aria-label="Категорія товару" value={form.category_id ?? ''} onChange={changeCategory}><option value="">Без категорії</option>{categories.map((c) => <option key={c.id} value={c.id}>{c.name}{!c.is_active ? ' · прихована' : ''}</option>)}</select></Field>
    <Field label="Субкатегорія" hint="Може існувати без категорії"><select className="input" aria-label="Субкатегорія товару" value={form.subcategory_id ?? ''} onChange={changeField(setForm, 'subcategory_id')}><option value="">Без субкатегорії</option>{available.map((s) => <option key={s.id} value={s.id}>{s.name}{s.category_name ? ` · ${s.category_name}` : ''}{!s.is_active ? ' · прихована' : ''}</option>)}</select></Field>
  </div>
}
export function PriceFields({ form, setForm }) {
  return <div className="stack">
    <div className="grid k2">
      <Field label="Ціна, ₴"><input className="input" aria-label="Ціна товару" type="number" min="0" step="0.01" required value={form.price ?? ''} onChange={changeField(setForm, 'price')} /></Field>
      <Field label="Стара ціна, ₴" hint="Відображається лише для акції"><input className="input" aria-label="Стара ціна товару" type="number" min="0" step="0.01" value={form.old_price ?? ''} onChange={changeField(setForm, 'old_price')} /></Field>
    </div>
    <label className="catalog-check"><input type="checkbox" checked={Boolean(form.is_sale)} onChange={changeField(setForm, 'is_sale')} />Акція — показувати знижку на вітрині та в боті</label>
  </div>
}
export function DisplayFields({ form, setForm }) {
  return <div className="stack">
    <div className="grid k2"><Field label="Залишок, шт"><input className="input" aria-label="Залишок товару" type="number" min="0" step="1" value={form.stock} onChange={changeField(setForm, 'stock')} /></Field><Field label="Порядок у каталозі"><input className="input" aria-label="Порядок товару" type="number" step="1" value={form.sort_order} onChange={changeField(setForm, 'sort_order')} /></Field></div>
    <label className="catalog-check"><input type="checkbox" checked={Boolean(form.is_active)} onChange={changeField(setForm, 'is_active')} />Показувати товар на вітрині та в боті</label>
    <label className="catalog-check"><input type="checkbox" checked={Boolean(form.is_new)} onChange={changeField(setForm, 'is_new')} />Новинка — позначка й розділ «Новинки»</label>
  </div>
}
export function DescriptionField({ form, setForm }) {
  return <Field label="Опис товару"><textarea className="input catalog-description-input" aria-label="Опис товару" value={form.description || ''} onChange={changeField(setForm, 'description')} placeholder="Особливості, характеристики та комплектація" /></Field>
}
export function ProductImageField({ form, setForm }) {
  return <ImageField label="Зображення товару" value={form.photo_url || ''} onChange={(photo_url) => setForm((old) => ({ ...old, photo_url }))} hint="Завантажте файл, виберіть зі сховища або вкажіть посилання. До 8 МБ." />
}

export function PerfumeFields({ form, setForm }) {
  return <div className="stack">
    <div className="grid k2">
      <Field label="Бренд парфуму"><input className="input" aria-label="Бренд парфуму" maxLength={100} value={form.brand || ''} onChange={changeField(setForm, 'brand')} placeholder="CREED" /></Field>
      <Field label="Обʼєм атомайзера, мл"><input className="input" aria-label="Обʼєм атомайзера" type="number" min="1" max="1000" step="1" value={form.volume_ml ?? ''} onChange={changeField(setForm, 'volume_ml')} placeholder="Не задано" /></Field>
      <Field label="Для кого"><select className="input" aria-label="Стать аромату" value={form.gender || 'unisex'} onChange={changeField(setForm, 'gender')}><option value="male">Чоловічий</option><option value="female">Жіночий</option><option value="unisex">Унісекс</option></select></Field>
    </div>
    <label className="catalog-check"><input type="checkbox" checked={Boolean(form.is_featured)} onChange={changeField(setForm, 'is_featured')} />Рекомендувати на головній сторінці</label>
    <p className="muted">Хіти визначаються автоматично за підтвердженими продажами за 90 днів; ця позначка керує окремою добіркою рекомендацій. Кожен обʼєм — окремий товар (SKU) зі своєю ціною та залишком. Ціна в усіх каналах є ціною за атомайзер, а сайт обчислює вартість за 1 мл.</p>
  </div>
}
export function perfumePayload(f) { return { brand: (f.brand || '').trim(), gender: f.gender || 'unisex', volume_ml: f.volume_ml === '' || f.volume_ml == null ? null : Number(f.volume_ml), is_featured: Boolean(f.is_featured) } }
