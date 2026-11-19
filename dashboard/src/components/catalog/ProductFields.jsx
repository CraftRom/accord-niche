import { Field } from '../ui'
import ImageField from '../ImageField'

export const emptyProduct = { brand_id: '', gender: 'unisex', volume_ml: '', is_featured: false, name: '', description: '', photo_url: '', price: '', old_price: '', stock: 0, sort_order: 0, is_active: true, is_new: false, is_sale: false }
export const changeField = (setForm, key) => (event) => setForm((form) => ({ ...form, [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }))
export function brandPayload(form) { return { brand_id: form.brand_id ? Number(form.brand_id) : null, ...(form.brand_id ? {} : { brand: '' }) } }
export function pricePayload(form) { return { price: Number(form.price), old_price: form.old_price === '' || form.old_price == null ? null : Number(form.old_price), is_sale: Boolean(form.is_sale) } }
export function validateProduct(form) {
  if (!form.name?.trim()) return 'Вкажіть назву товару'
  if (form.volume_ml !== '' && form.volume_ml != null && (!Number.isInteger(Number(form.volume_ml)) || Number(form.volume_ml) < 1 || Number(form.volume_ml) > 1000)) return 'Обʼєм має бути цілим числом від 1 до 1000 мл'
  if (form.price === '' || !Number.isFinite(Number(form.price)) || Number(form.price) < 0) return 'Вкажіть невід’ємну ціну'
  if (form.is_sale && (!form.old_price || Number(form.old_price) <= Number(form.price))) return 'Для акції стара ціна має бути більшою за поточну'
  if (!Number.isInteger(Number(form.stock)) || Number(form.stock) < 0) return 'Залишок має бути цілим невід’ємним числом'
  return ''
}
// Бренд замість категорії: товар обирає бренд зі списку. Новий бренд
// додається в «Бренди» над каталогом, тож назва пишеться однаково скрізь.
export function BrandFields({ form, setForm, brands, onManage }) {
  return <div className="stack">
    <Field label="Бренд" hint="Аромат шукають саме за брендом: на сайті, в Mini App і в боті"><select className="input" aria-label="Бренд товару" value={form.brand_id ?? ''} onChange={changeField(setForm, 'brand_id')}>
      <option value="">Без бренду</option>
      {brands.map((b) => <option key={b.id} value={b.id}>{b.name}{!b.is_active ? ' · прихований' : ''}</option>)}
    </select></Field>
    {onManage && <button type="button" className="btn ghost small" onClick={onManage}>Додати або змінити бренд</button>}
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
      <Field label="Обʼєм атомайзера, мл"><input className="input" aria-label="Обʼєм атомайзера" type="number" min="1" max="1000" step="1" value={form.volume_ml ?? ''} onChange={changeField(setForm, 'volume_ml')} placeholder="Не задано" /></Field>
      <Field label="Для кого"><select className="input" aria-label="Стать аромату" value={form.gender || 'unisex'} onChange={changeField(setForm, 'gender')}><option value="male">Чоловічий</option><option value="female">Жіночий</option><option value="unisex">Унісекс</option></select></Field>
    </div>
    <label className="catalog-check"><input type="checkbox" checked={Boolean(form.is_featured)} onChange={changeField(setForm, 'is_featured')} />Рекомендувати на головній сторінці</label>
    <p className="muted">Хіти визначаються автоматично за підтвердженими продажами за 90 днів; ця позначка керує окремою добіркою рекомендацій. Кожен обʼєм — окремий товар (SKU) зі своєю ціною та залишком. Ціна в усіх каналах є ціною за атомайзер, а сайт обчислює вартість за 1 мл.</p>
  </div>
}
export function perfumePayload(f) { return { gender: f.gender || 'unisex', volume_ml: f.volume_ml === '' || f.volume_ml == null ? null : Number(f.volume_ml), is_featured: Boolean(f.is_featured) } }
