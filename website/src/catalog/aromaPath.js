/** Readable aroma address: /aroma/<id>-<brand-name>. The server sends `path` and `slug`. */
export const AROMA_ROUTE = /^\/aroma\/(\d+)(?:-[a-z0-9-]+)?$/
export function aromaPath(item, productId) {
  const id = productId || item?.default_product_id || item?.id
  if (!item?.slug) return '/aroma/' + id
  // The aroma itself (first SKU) is its canonical page; a volume adds its own id.
  return productId || !item.path ? '/aroma/' + id + '-' + item.slug : item.path
}
