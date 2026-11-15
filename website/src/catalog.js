/** Product identity is the DB row's id. Each sellable volume is a separate SKU. */
export const genderName = { male: 'чоловічий', female: 'жіночий', unisex: 'унісекс' }

/** Link payload has no prices or personally identifiable info. Prices are server-authoritative. */
export function cartStartParam(cart, products) {
  const valid = Object.entries(cart).map(([id, qty]) => ({ id:Number(id), qty:Number(qty) }))
    .filter(p => Number.isSafeInteger(p.id) && p.id > 0 && Number.isInteger(p.qty) && p.qty > 0 && p.qty <= 99
      && products.some(item => item.id === p.id && item.stock > 0))
  if (valid.length > 20) return ''
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
  for (const [key, value] of Object.entries(cart).slice(0,30)) {
    const id = Number(key)
    const qty = Number(value)
    const product = byId.get(id)
    if (!Number.isSafeInteger(id) || id <= 0 || !product || !Number.isInteger(qty) || qty <= 0) continue
    const capped = Math.min(qty, 99, Math.max(0, Number(product.stock) || 0))
    if (capped > 0) valid[id] = capped
  }
  return valid
}
