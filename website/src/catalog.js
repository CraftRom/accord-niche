/** Product identity is the DB row's id. Each sellable volume is a separate SKU. */
export const featuredReference = [
  ['CREED', 'Aventus', 'male'],
  ['KILIAN', 'Good Girl Gone Bad', 'female'],
  ['NASOMATTO', 'Black Afgano', 'male'],
  ['KILIAN', "Angels’ Share", 'female'],
  ['AMOUAGE', 'Guidance', 'female'],
  ['HORMONE PARIS', 'Gaba', 'female'],
  ['27 87', 'Genetic Bliss', 'unisex'],
  ['ORTO PARISI', 'Risvelium', 'male'],
]
export const genderName = { male: 'чоловічий', female: 'жіночий', unisex: 'унісекс' }

export function baseName(product) {
  const name = String(product.name || '').trim()
  return name.replace(/\s*[-–—,(]?\s*(?:2|5|10|15|20|30|50|100)\s*(?:мл|ml)\s*\)?$/i, '').trim() || name
}
export function normalize(value) {
  return String(value || '').normalize('NFKD').toLowerCase()
    .replace(/[’'`´]/g, '').replace(/[^a-zа-яіїєґ0-9]+/gi, '')
}
export function unitPrice(product) {
  const volume = Number(product.volume_ml)
  const price = Number(product.price)
  return volume > 0 && Number.isFinite(price) ? price / volume : null
}
export function groupProducts(items) {
  const groups = new Map()
  for (const item of items) {
    const name = baseName(item)
    const brand = String(item.brand || '').trim()
    const key = normalize(brand) + ':' + normalize(name)
    if (!groups.has(key)) groups.set(key, {
      key, id: item.id, brand, name, gender: item.gender || 'unisex',
      description: item.description || '', is_featured: false, is_new: false,
      variants: [],
    })
    const g = groups.get(key)
    g.variants.push(item)
    g.is_featured ||= Boolean(item.is_featured)
    g.is_new ||= Boolean(item.is_new)
  }
  return [...groups.values()].map(g => {
    g.variants.sort((a,b) => (a.volume_ml || 999) - (b.volume_ml || 999) || Number(a.price)-Number(b.price))
    g.pricePerMl = g.variants.reduce((m,p) => { const unit = unitPrice(p); return unit == null ? m : m == null ? unit : Math.min(m,unit) }, null)
    g.image = g.variants.find(v => v.photo_url || v.photo_endpoint)?.photo_url || g.variants.find(v => v.photo_endpoint)?.photo_endpoint || ''
    g.stock = g.variants.reduce((sum,v) => sum+Math.max(0, v.stock || 0), 0)
    return g
  })
}
export function referenceCards(groups) {
  return featuredReference.map(([brand,name,gender]) => {
    const match = groups.find(g => normalize(g.brand) === normalize(brand) && normalize(g.name) === normalize(name))
    return match || { key: `preview:${normalize(brand)}:${normalize(name)}`, id: null, brand, name, gender, preview: true, variants: [], pricePerMl: null }
  })
}
/** Link payload has no prices or personally identifiable info. Prices are server-authoritative. */
export function cartStartParam(cart, products) {
  const valid = Object.entries(cart).map(([id, qty]) => ({ id:Number(id), qty:Number(qty) }))
    .filter(p => Number.isSafeInteger(p.id) && p.id > 0 && Number.isInteger(p.qty) && p.qty > 0 && p.qty <= 99
      && products.some(item => item.id === p.id && item.stock > 0))
    .slice(0, 20)
  const data = valid.map(({id,qty}) => `${id}x${qty}`).join('-')
  const param = `cart_${data}`
  return data && param.length <= 512 ? param : ''
}
export function telegramCheckoutUrl(base, cart, products) {
  if (!/^https:\/\/t\.me\/[A-Za-z0-9_]+\/[A-Za-z0-9_]+\/?$/.test(base)) return ''
  const param = cartStartParam(cart,products)
  return param ? `${base.replace(/\/$/,'')}?startapp=${param}` : ''
}

/** Browser storage is untrusted and can contain orphaned/deleted SKUs. */
export function sanitizeCart(cart, products) {
  if (!cart || typeof cart !== 'object' || Array.isArray(cart)) return {}
  const byId = new Map(products.map(p => [p.id, p]))
  const valid = {}
  for (const [key, value] of Object.entries(cart)) {
    const id = Number(key)
    const qty = Number(value)
    const product = byId.get(id)
    if (!Number.isSafeInteger(id) || id <= 0 || !product || !Number.isInteger(qty) || qty <= 0) continue
    const capped = Math.min(qty, 99, Math.max(0, Number(product.stock) || 0))
    if (capped > 0) valid[id] = capped
  }
  return valid
}
