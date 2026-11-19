import { useEffect } from 'react'
import BlogContent from '../blog/BlogContent'
import { StateBlock, errorTitle } from '../ui/states'
import { useStoreRequest } from '../useStoreRequest'

// Public offer and privacy policy. The text is edited in the dashboard
// («Документи»); seller requisites are filled in on the server.
const TITLES = { terms: 'Публічна оферта', privacy: 'Політика конфіденційності' }

export function LegalPage({ docKey, go }) {
  const request = useStoreRequest('/api/public/legal/' + docKey, 0)
  const doc = request.data
  useEffect(() => {
    const previous = document.title
    document.title = TITLES[docKey] + ' — ACCORD NICHE'
    return () => { document.title = previous }
  }, [docKey])
  return <main className="shell blog-page blog-article legal-page">
    <header className="blog-heading"><p className="eyebrow">ДОКУМЕНТИ</p><h1>{TITLES[docKey]}</h1></header>
    {!doc && request.loading && <StateBlock kind="loading">Завантажуємо документ…</StateBlock>}
    {!doc && request.error && <StateBlock kind="error" title={errorTitle(request, 'Документ не знайдено')}
      action={<button className="btn outline" onClick={request.retry}>Спробувати ще раз</button>}><p>{request.error}</p></StateBlock>}
    {doc && <>
      <BlogContent body={doc.body}/>
      <nav className="legal-switch" aria-label="Інші документи">
        {docKey === 'terms'
          ? <button className="text-muted-button" onClick={() => go('/privacy')}>Політика конфіденційності →</button>
          : <button className="text-muted-button" onClick={() => go('/terms')}>Публічна оферта →</button>}
      </nav>
    </>}
  </main>
}
