// W-27: one system for loading, error, empty and success states. Every screen
// (catalog, product, profile, blog, checkout) says the same kind of thing the
// same way, and a screen reader hears it: errors are alerts, loading is a
// polite status. Messages separate «no connection / timeout», «not found» and
// «nothing here yet»; nothing is ever replaced with invented zeros.

/** Title for a failed request, by its kind. */
export function errorTitle(request, notFound = 'Сторінку не знайдено') {
  if ([404, 410].includes(request?.errorStatus)) return notFound
  if (!request?.errorStatus) return 'Немає зв’язку з магазином'
  return 'Не вдалося завантажити дані'
}

export function StateBlock({kind = 'empty', title, children, action, className = '', headingLevel = 2}) {
  const Heading = 'h' + headingLevel
  const role = kind === 'error' ? 'alert' : kind === 'loading' || kind === 'success' ? 'status' : undefined
  return <div className={`state-block state-${kind} ${className}`.trim()} role={role}>
    {kind === 'loading' && <span className="loading-dot" aria-hidden="true"/>}
    {title && <Heading className="state-title">{title}</Heading>}
    {children && <div className="state-text">{children}</div>}
    {action}
  </div>
}

/** Short inline message next to a form or a list: error, success or hint. */
export function InlineAlert({kind = 'error', children}) {
  if (!children) return null
  return <p className={kind === 'error' ? 'shop-error inline-alert' : kind === 'success' ? 'shop-success inline-alert' : 'shop-hint inline-alert'}
    role={kind === 'error' ? 'alert' : 'status'}>{children}</p>
}
