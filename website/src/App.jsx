import { useEffect, useState } from 'react'
import { useCommerce } from './account/useCommerce'
import { BlogArticle, BlogList } from './blog/BlogPages'
import { Basket } from './cart/CartDrawer'
import { sanitizeCart } from './catalog'
import { Brands } from './catalog/BrandsPage'
import { Catalog } from './catalog/CatalogPage'
import { Detail } from './catalog/ProductPage'
import { AROMA_ROUTE } from './catalog/aromaPath'
import { recordVisit, rememberCampaign } from './checkout'
import { CheckoutPage } from './checkout/CheckoutPage'
import { CheckoutSuccess } from './checkout/CheckoutSuccess'
import { money } from './format'
import { Home, HowItWorks } from './home/HomePage'
import { Footer } from './layout/Footer'
import { Header } from './layout/Header'
import { InfoModal } from './layout/InfoModal'
import { CART_KEY, TestModeBanner } from './layout/TestModeBanner'
import { startReveal } from './motion'
import { ProfilePage } from './profile/ProfilePage'
import { useRoute } from './router'
import { LegalPage } from './legal/LegalPage'
import { PageTitle } from './ui/PageTitle'
import { useStoreRequest } from './useStoreRequest'

export default function App() {
  const [route, go] = useRoute()
  useEffect(() => startReveal(), [])
  // UTM first, then the visit, so the visit carries the landing campaign.
  useEffect(()=>{rememberCampaign(location.search);recordVisit()},[route])
  const path = route.split('?')[0].replace(/\/+$/, '') || '/'
  const commerce = useCommerce()
  const [orderResult, setOrderResult] = useState(null)
  const [products, setProducts] = useState([])
  const [basketOpen, setBasketOpen] = useState(false)
  const [info, setInfo] = useState('')
  const [notice, setNotice] = useState('')
  const [lineNotes, setLineNotes] = useState({})
  const [cart, setCart] = useState(() => {try {
    const saved = JSON.parse(localStorage.getItem(CART_KEY) || '{}')
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? Object.fromEntries(Object.entries(saved).filter(([id,qty]) => /^[1-9][0-9]*$/.test(id) && Number.isSafeInteger(Number(id)) && Number.isInteger(Number(qty)) && Number(qty) > 0).slice(0,30)) : {}
  } catch {return {}}})
  const ids = Object.keys(cart).sort((a,b) => Number(a) - Number(b)).join(',')
  const cartRequest = useStoreRequest(ids ? '/api/public/products?ids=' + ids : null)
  const siteRequest = useStoreRequest('/api/public/site-config')
  const site = siteRequest.data || {}
  useEffect(() => {try {localStorage.setItem(CART_KEY, JSON.stringify(cart))} catch {}}, [cart])
  useEffect(() => {
    if (Array.isArray(cartRequest.data)) {
      const next=sanitizeCart(cart,cartRequest.data)
      const changed=JSON.stringify(next)!==JSON.stringify(cart)
      const repriced=cartRequest.data.some(product=>products.some(previous=>previous.id===product.id && Number(previous.price)!==Number(product.price)))
      // W-11: say on the line itself what changed, not only in a page-wide notice.
      const notes={}
      for(const product of cartRequest.data){
        const previous=products.find(item=>item.id===product.id)
        const before=Number(cart[product.id])||0, after=Number(next[product.id])||0
        const parts=[]
        if(previous && Number(previous.price)!==Number(product.price))parts.push('Ціна оновилась: було '+money(previous.price)+', тепер '+money(product.price))
        if(after>0 && after<before)parts.push('Кількість зменшено до '+after+': більше немає в наявності')
        if(parts.length)notes[product.id]=parts.join('. ')
      }
      setLineNotes(notes)
      setProducts(cartRequest.data)
      if(changed){setCart(next);setNotice('Наявність змінилася. Недоступні позиції прибрано, кількість обмежено поточним залишком. Перевірте кошик.')}
      else if(repriced)setNotice('Ціни в кошику оновлено. Перевірте підсумок перед підтвердженням замовлення.')
    }
  }, [cartRequest.data])
  function change(id, qty) {
    setLineNotes(old => {if (!(id in old)) return old; const next = {...old}; delete next[id]; return next})
    setCart(old => {const next = {...old}; const product = products.find(product => product.id === id); const capped = Math.min(Math.max(0,qty), product?.stock || 0, 99); if (capped) next[id] = capped; else delete next[id]; return next})
  }
  function add(product) {
    if (!cart[product.id] && Object.keys(cart).length >= 30) {setNotice('У кошику може бути до 30 різних позицій.'); return}
    setProducts(old => [...old.filter(item => item.id !== product.id), product])
    setCart(old => ({...old, [product.id]: Math.min((Number(old[product.id]) || 0) + 1, product.stock, 99)}))
    setBasketOpen(true)
  }
  const detail = path.match(AROMA_ROUTE)
  const blogMatch = path.match(/^\/blog\/([^/]+)$/)
  let blogSlug = blogMatch?.[1] || ''
  try { blogSlug = decodeURIComponent(blogSlug) } catch {}
  useEffect(() => {
    const destination = new URLSearchParams(route.split('?')[1] || '').get('returnTo') || ''
    if (path === '/profile' && (commerce.account.signed_in || commerce.account.phone_verified || commerce.account.telegram_linked) && /^\/blog\/[^/?#]+$/.test(destination)) go(destination, {replace:true})
  }, [route, commerce.account.signed_in, commerce.account.phone_verified, commerce.account.telegram_linked])
  // Sign out from the header (next to the cart) or the profile: one action.
  async function logout() {
    try {await commerce.request('/auth/logout', 'POST'); await commerce.refresh(); setNotice('Ви вийшли з профілю.')}
    catch (error) {setNotice(error.message || 'Не вдалося вийти. Спробуйте ще раз.')}
  }
  const count = Object.values(cart).reduce((sum,qty) => sum + Number(qty), 0)
  return <><TestModeBanner/><Header route={route} go={go} onCart={() => setBasketOpen(true)} onLogout={logout} count={count} account={commerce.account}/>
    {notice && <div className="shell notice" role="alert">{notice}<button onClick={() => setNotice('')}>Закрити</button></div>}
    {path === '/' ? <Home go={go}/> : path === '/catalog' || path === '/sets' ? <Catalog key={path} route={route} go={go} sets={path === '/sets'}/> : path === '/brands' ? <Brands go={go}/> : path === '/blog' ? <BlogList route={route} go={go}/> : blogMatch ? <BlogArticle key={blogSlug} slug={blogSlug} shop={commerce} go={go}/> : detail ? <Detail id={Number(detail[1])} go={go} add={add}/> : path === '/checkout' ? <CheckoutPage site={site} shop={commerce} cart={cart} products={products} cartRequest={cartRequest} change={change} go={go} complete={result => {setOrderResult(result); setNotice(''); setCart({})}}/> : path === '/profile' ? <ProfilePage key={commerce.account.account_key || 'guest'} shop={commerce} go={go}/> : path === '/order/success' ? <CheckoutSuccess result={commerce.account.has_session?orderResult:null} go={go}/> : path === '/terms' || path === '/privacy' ? <LegalPage key={path} docKey={path.slice(1)} go={go}/> : path === '/how' ? <main><PageTitle label="ПРОСТО І ЗРОЗУМІЛО" title="Як це працює"/><HowItWorks/></main> : <main><PageTitle label="404" title="Сторінку не знайдено"/><div className="shell"><button className="btn outline" onClick={() => go('/')}>На головну</button></div></main>}
    <Footer go={go} setInfo={setInfo} site={site}/><Basket lineNotes={lineNotes} open={basketOpen} close={() => setBasketOpen(false)} cart={cart} products={products} change={change} go={go} site={site} request={cartRequest}/><InfoModal name={info} close={() => setInfo('')} site={site}/>
  </>
}
