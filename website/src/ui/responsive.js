// Uploaded images come in WebP copies of these widths (backend image_variants).
// The browser picks the smallest one that fits the slot: phones no longer
// download multi-megabyte originals for a product card.
export const WIDTHS = [320, 640, 960, 1600]

export function responsiveSource(url) {
  if (!url) return null
  let base = null
  if (/^\/api\/public\/catalog\/\d+\/photo$/.test(url)) base = url
  const media = url.match(/^\/media\/([A-Za-z0-9_-]+\.(?:png|jpe?g|webp|gif))$/i)
  if (media) base = '/api/public/media/' + media[1]
  if (!base) return null
  return {src: base + '?w=960', srcSet: WIDTHS.map(width => `${base}?w=${width} ${width}w`).join(', ')}
}
