// Google result preview with length hints. Google shows about 60 characters of
// a title and 150–160 of a description; longer text is cut with "…".
export const SEO_LIMITS = { title: [30, 60], description: [70, 160] }

export function lengthState(value, [min, max]) {
  const length = (value || '').trim().length
  if (!length) return ['muted', 'порожньо — буде створено автоматично']
  if (length > max) return ['seo-warn', `${length} — задовге, Google обріже`]
  if (length < min) return ['seo-warn', `${length} — закоротке`]
  return ['seo-ok', `${length} — оптимально`]
}

export function Counter({ value, limits }) {
  const [tone, text] = lengthState(value, limits)
  return <small className={'seo-counter ' + tone}>{text}</small>
}

const cut = (text, max) => text.length > max ? text.slice(0, max - 1).trimEnd() + '…' : text

export function SeoSnippet({ title, description, url }) {
  return <div className="seo-snippet" aria-label="Попередній вигляд у Google">
    <span className="seo-snippet-url">{url}</span>
    <strong className="seo-snippet-title">{cut(title || 'Заголовок сторінки', 62)}</strong>
    <p className="seo-snippet-description">{cut(description || 'Опис сторінки в результатах пошуку.', 160)}</p>
  </div>
}
