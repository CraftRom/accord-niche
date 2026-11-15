import { useEffect, useMemo, useState } from 'react'
import { cartStartParam, featuredReference, genderName, groupProducts, referenceCards, sanitizeCart, telegramCheckoutUrl } from './catalog'
import { useCommerce, CheckoutPage, CheckoutSuccess, ProfilePage } from './commerce'

const PUBLIC_CATALOG = '/api/public/catalog'
const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const fmt = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 2 })

function useRoute() {
  const read = () => decodeURI(location.pathname.slice(BASE.length) || '/')
  const [path, setPath] = useState(read)
  useEffect(() => {
    const pop = () => setPath(read())
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])
  const go = (to) => {
    const next = `${BASE}${to}`
    if (location.pathname !== next) history.pushState(null, '', next)
    setPath(to)
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
  return [path, go]
}

function Icon({ name, size = 21 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }
  if (name === 'search') return <svg {...common}><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></svg>
  if (name === 'user') return <svg {...common}><circle cx="12" cy="8" r="4"/><path d="M4.5 21c0-4 3.2-6 7.5-6s7.5 2 7.5 6"/></svg>
  if (name === 'bag') return <svg {...common}><path d="M4 8h16l-1.2 13H5.2L4 8Z"/><path d="M9 9V6a3 3 0 0 1 6 0v3"/></svg>
  if (name === 'close') return <svg {...common}><path d="m5 5 14 14M19 5 5 19"/></svg>
  if (name === 'menu') return <svg {...common}><path d="M3 7h18M3 12h18M3 17h18"/></svg>
  return <svg {...common}><path d="M4 12h16m-7-7 7 7-7 7"/></svg>
}

function Logo({ dark = false, onClick }) {
  return <button className={`brandmark${dark ? ' inverse' : ''}`} onClick={onClick} aria-label="ACCORD NICHE — на головну">
    <strong>ACCORD</strong><span className="brandmark-bottom"><i/>NICHE<i/></span>
  </button>
}

function Header({ go, query, setQuery, onCart, count, account }) {
  const [search, setSearch] = useState(false)
  const [menu, setMenu] = useState(false)
  const nav = [ ['/catalog', 'Каталог'], ['/sets', 'Набори пробників'], ['/brands', 'Бренди'], ['/how', 'Як це працює'], ['/blog', 'Блог'] ]
  const navClick = (p) => { go(p); setMenu(false); setSearch(false) }
  return <header className="header">
    <div className="shell header-inner">
      <Logo onClick={() => navClick('/')} />
      <nav className={`header-nav${menu ? ' open' : ''}`} aria-label="Головна навігація">
        {nav.map(([p, label]) => <button key={p} type="button" onClick={() => navClick(p)}>{label}</button>)}
      </nav>
      <div className="header-actions">
        <button className="icon-btn" title={account?.signed_in ? "Мій профіль" : "Особистий кабінет"} aria-label="Профіль" onClick={()=>navClick('/profile')}><Icon name="user"/></button>
        <button className="icon-btn" aria-label="Пошук" title="Пошук ароматів" onClick={() => setSearch(v => !v)}><Icon name="search" /></button>
        <button className="icon-btn cart-button" aria-label={`Кошик, товарів ${count}`} title="Кошик" onClick={onCart}><Icon name="bag"/>{count > 0 && <span className="cart-count">{count}</span>}</button>
        <button className="icon-btn menu-btn" aria-label="Меню" aria-expanded={menu} onClick={() => setMenu(v => !v)}><Icon name={menu ? 'close':'menu'} /></button>
      </div>
    </div>
    {search && <form className="search-strip shell" onSubmit={event => {event.preventDefault();navClick('/catalog')}} role="search"><Icon name="search" /><input aria-label="Пошук за брендом або ароматом" autoFocus placeholder="Знайти аромат або бренд…" value={query} onChange={e => setQuery(e.target.value)} /><button className="text-action" type="submit">Знайти <Icon name="arrow" size={16}/></button></form>}
  </header>
}

function ImageTile({ item, hero = false }) {
  if (!hero && item?.image) return <div className="photo-tile"><img loading="lazy" src={item.image} alt={`${item.brand} ${item.name}`} referrerPolicy="no-referrer" onError={event => { event.currentTarget.style.display = 'none' }} /></div>
  return <div className={`photo-tile placeholder${hero ? ' hero-tile' : ''}`}><span>{hero ? '[ФОТО: АТОМАЙЗЕРИ НА ТЛІ КАМЕНЮ / ТКАНИНИ]' : '[ФОТО ФЛАКОНА]'}</span></div>
}

function Hero({ go }) {
  return <section className="hero shell" aria-labelledby="hero-title">
    <div className="hero-content">
      <p className="eyebrow">РОЗПИВ ОРИГІНАЛЬНОЇ НІШЕВОЇ ПАРФУМЕРІЇ</p>
      <h1 id="hero-title">Спробуй аромат,<br />перш ніж купити<br />флакон</h1>
      <p className="hero-description">Creed, Kilian, Nasomatto, Amouage та інші — від 2 мл. Носи аромат тиждень, а не пшик на блотері.</p>
      <div className="hero-cta"><button className="btn primary" onClick={() => go('/catalog')}>ОБРАТИ АРОМАТ</button><button className="btn outline" onClick={() => go('/sets')}>НАБІР ПРОБНИКІВ</button></div>
    </div>
    <ImageTile hero />
  </section>
}

function HowItWorks({ compact = false }) {
  return <section id="how-it-works" className={`how-section${compact ? ' how-full' : ''}`} aria-labelledby="how-title">
    <div className="shell">
      <h2 id="how-title" className="section-heading light">Як це працює</h2>
      <div className="steps">
        <article><span className="step-number">01</span><h3>Обираєш аромат і об’єм</h3><p>2, 5 або 10 мл — від пробника до дорожнього флакона.</p></article>
        <article><span className="step-number">02</span><h3>Розливаємо з оригінального флакона</h3><p>В окремий атомайзер з маркуванням: назва, об’єм, дата розливу.</p></article>
        <article><span className="step-number">03</span><h3>Доставляємо по Україні</h3><p>Новою поштою. Сподобався аромат — замов більший об’єм.</p></article>
      </div>
    </div>
  </section>
}

function ProductCard({ item, go }) {
  const details = Boolean(item.id)
  const showPrice = item.pricePerMl != null
  return <article className={`product-card${details ? ' available' : ' editorial'}`}>
    <button type="button" className="product-link" onClick={() => details && go(`/aroma/${item.id}`)} disabled={!details} aria-label={`${item.brand} ${item.name}${details ? ' — подивитися' : ' — скоро в каталозі'}`}>
      <ImageTile item={item} />
      <div className="product-meta"><span className="product-brand">{item.brand}</span><h3>{item.name}</h3><p>{genderName[item.gender] || 'унісекс'}</p><strong>{showPrice ? `від ${fmt.format(item.pricePerMl)} грн / мл` : 'від [ЦІНА] грн / мл'}</strong></div>
    </button>
  </article>
}

function Featured({ groups, go }) {
  const cards = referenceCards(groups)
  return <section className="featured shell" aria-labelledby="featured-title">
    <div className="section-row"><h2 id="featured-title" className="section-heading">Хіти розливу</h2><button className="section-link" onClick={() => go('/catalog')}>ВЕСЬ КАТАЛОГ <span aria-hidden="true">→</span></button></div>
    <div className="products-grid">{cards.map(p => <ProductCard key={p.key} item={p} go={go} />)}</div>
  </section>
}

function Authenticity() {
  return <section className="authenticity" aria-labelledby="auth-title"><div className="shell authenticity-grid"><div><p className="eyebrow">ТІЛЬКИ ОРИГІНАЛИ</p><h2 id="auth-title">Показуємо, звідки кожен флакон</h2></div><div className="proof-grid"><article><h3>Партійний код на відео</h3><p>Знімаємо код флакона й коробки перед розливом.</p></article><article><h3>Документи постачальника</h3><p>Купуємо по безготівці з накладними.</p></article><article><h3>Розливи при тобі</h3><p>Процес розливу — у наших TikTok та Instagram.</p></article></div></div></section>
}

function Footer({ go, setInfo, site }) {
  const INSTAGRAM=site.instagram_url || ''
  const TIKTOK=site.tiktok_url || ''
  const PHONE=site.phone || ''
  return <footer className="footer"><div className="shell footer-inner"><div className="footer-brand"><Logo dark onClick={() => go('/')} /><span>accordniche.pp.ua</span></div><div className="footer-links"><div><button onClick={() => setInfo('delivery')}>Доставка й оплата</button><button onClick={() => setInfo('returns')}>Повернення</button><button onClick={() => setInfo('about')}>Про нас</button></div><div>{INSTAGRAM ? <a href={INSTAGRAM} target="_blank" rel="noopener noreferrer">Instagram</a> : <span>Instagram</span>}{TIKTOK ? <a href={TIKTOK} target="_blank" rel="noopener noreferrer">TikTok</a> : <span>TikTok</span>}{PHONE ? <a href={`tel:${PHONE.replace(/[^+\d]/g, '')}`}>{PHONE}</a> : <span>[ВАШ ТЕЛЕФОН]</span>}</div></div></div></footer>
}

function PageTitle({ label, title, detail }) {
  return <div className="page-title shell"><p className="eyebrow">{label}</p><h1>{title}</h1>{detail && <p>{detail}</p>}</div>
}

function Catalog({ groups, go, query, setQuery, error, loading, initialGender = '' }) {
  const [gender,setGender] = useState(initialGender)
  const [brand,setBrand] = useState('')
  const [sort,setSort] = useState('featured')
  const brands = [...new Set(groups.map(g=>g.brand).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'uk'))
  const list = groups.filter(g => (!gender || g.gender === gender) && (!brand || g.brand === brand) && (!query || `${g.brand} ${g.name}`.toLowerCase().includes(query.toLowerCase())) )
    .sort((a,b) => sort==='price' ? (a.pricePerMl??Infinity)-(b.pricePerMl??Infinity) : sort==='name' ? a.name.localeCompare(b.name,'uk') : Number(b.is_featured)-Number(a.is_featured))
  return <main><PageTitle label="КОЛЕКЦІЯ АРОМАТІВ" title="Каталог" detail="Оберіть аромат і потрібний об’єм — від першого знайомства до дорожнього формату." />
    <section className="shell catalog-layout" aria-label="Каталог ароматів"><div className="catalog-filters"><label>ПОШУК<input value={query} placeholder="Назва, бренд…" onChange={e=>setQuery(e.target.value)} /></label><label>БРЕНД<select value={brand} onChange={e=>setBrand(e.target.value)}><option value="">Усі бренди</option>{brands.map(b=><option key={b}>{b}</option>)}</select></label><label>АРОМАТ ДЛЯ<select value={gender} onChange={e=>setGender(e.target.value)}><option value="">Для всіх</option><option value="female">Жіночий</option><option value="male">Чоловічий</option><option value="unisex">Унісекс</option></select></label><label>СОРТУВАННЯ<select value={sort} onChange={e=>setSort(e.target.value)}><option value="featured">Рекомендовані</option><option value="name">За назвою</option><option value="price">За ціною за мл</option></select></label><button className="filter-reset" onClick={()=>{setBrand('');setGender('');setSort('featured');setQuery('')}}>Скинути фільтри</button></div>
    <div className="catalog-results"><div className="catalog-summary"><span>{loading ? 'Завантажуємо каталог…' : `${list.length} ароматів`}</span></div>{error && <div className="notice" role="alert">Не вдалося оновити каталог: {error}</div>}{!loading && !list.length && !error && <div className="notice">У каталозі ще немає ароматів за цими фільтрами. Спробуйте інший пошук.</div>}<div className="products-grid">{list.map(p=><ProductCard key={p.key} item={p} go={go}/>)}</div></div></section>
  </main>
}

function Detail({ group, add, go }) {
  const [sku,setSku] = useState(group?.variants[0]?.id || '')
  useEffect(()=>setSku(group?.variants[0]?.id || ''), [group?.id])
  if (!group) return <main><PageTitle label="АРОМАТ" title="Аромат не знайдено" /><div className="shell"><button className="btn outline" onClick={()=>go('/catalog')}>До каталогу</button></div></main>
  const current=group.variants.find(p=>p.id===Number(sku)) || group.variants[0]
  return <main><div className="shell detail-back"><button onClick={()=>go('/catalog')}>← Усі аромати</button></div><section className="shell detail-grid"><ImageTile item={group}/><div className="detail-text"><p className="eyebrow">{group.brand}</p><h1>{group.name}</h1><p className="detail-kind">{genderName[group.gender] || 'унісекс'} · оригінальна нішева парфумерія</p>{group.description && <p className="detail-description">{group.description}</p>}<div className="variant-group"><h2>Обери об’єм</h2><div className="variant-buttons">{group.variants.map(v=><button key={v.id} disabled={v.stock<=0} className={v.id===current.id?'selected':''} onClick={()=>setSku(v.id)}>{v.volume_ml ? `${v.volume_ml} мл` : v.name}{v.stock<=0 && <small>Немає</small>}</button>)}</div></div><div className="detail-buy"><div><span>ЦІНА ЗА АТОМАЙЗЕР</span><strong>{fmt.format(Number(current.price))} грн</strong>{current.volume_ml && <p>{fmt.format(Number(current.price)/current.volume_ml)} грн / мл</p>}</div><button className="btn primary" disabled={current.stock<=0} onClick={()=>add(current)}>{current.stock>0 ? 'ДОДАТИ В КОШИК' : 'НЕМАЄ В НАЯВНОСТІ'}</button></div><p className="microcopy">Залишки та ціни оновлюються з єдиного каталогу магазину.</p></div></section></main>
}

function Basket({ open, close, cart, products, change, go, site }) {
  if (!open) return null
  const lines = Object.entries(cart).map(([id,qty])=>({product:products.find(p=>p.id===Number(id)),qty:Number(qty)})).filter(x=>x.product)
  const total=lines.reduce((sum,x)=>sum+Number(x.product.price)*x.qty,0)
  const link=telegramCheckoutUrl(site.miniapp_url || '',cart,products)
  return <div className="drawer-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)close()}}><aside role="dialog" aria-modal="true" aria-label="Кошик" className="basket"><div className="basket-head"><h2>Кошик <span>({lines.reduce((n,l)=>n+l.qty,0)})</span></h2><button className="icon-btn" aria-label="Закрити кошик" onClick={close}><Icon name="close" /></button></div><div className="basket-lines">{lines.length ? lines.map(({product,qty})=><div className="basket-line" key={product.id}><div className="basket-thumb">[ФОТО]</div><div className="basket-info"><h3>{product.brand} · {product.name}</h3><p>{product.volume_ml ? `${product.volume_ml} мл` : 'Аромат'}</p><strong>{fmt.format(Number(product.price)*qty)} грн</strong><div className="qty-control"><button aria-label="Зменшити кількість" onClick={()=>change(product.id,qty-1)}>-</button><span>{qty}</span><button disabled={qty>=product.stock || qty>=99} aria-label="Збільшити кількість" onClick={()=>change(product.id,qty+1)}>+</button><button className="remove-btn" onClick={()=>change(product.id,0)}>Видалити</button></div></div></div>) : <div className="empty-basket"><p>У кошику поки порожньо</p><button className="btn outline" onClick={()=>{close();go('/catalog')}}>Переглянути аромати</button></div>}</div>{lines.length>0 && <div className="basket-bottom"><div className="basket-total"><span>Разом</span><strong>{fmt.format(total)} грн</strong></div><button className="btn primary checkout-link" onClick={()=>{close();go('/checkout')}}>ОФОРМИТИ ЗАМОВЛЕННЯ <Icon name="arrow" size={16}/></button>{link && <a className="basket-telegram-link" href={link} target="_blank" rel="noopener noreferrer">Або продовжити в Telegram Mini App</a>}<p>Замовлення оформлюється на цьому сайті без Telegram. Наявність і ціни перевіряються перед покупкою.</p></div>}</aside></div>
}

function Sets({ groups, go }) {
  const kits=groups.filter(g=>/набір|пробник|set|discovery/i.test(g.name))
  return <main><PageTitle label="ЗНАЙОМСТВО З АРОМАТАМИ" title="Набори пробників" detail="Кілька ароматів, щоб знайти свій. Набори з'являються в каталозі після додавання в dashboard." /><div className="shell collections-section">{kits.length ? <div className="products-grid">{kits.map(g=><ProductCard key={g.key} item={g} go={go}/>)}</div> : <div className="collection-empty"><h2>Почни з малого</h2><p>Обери окремі пробники від 2 мл у каталозі. Готові набори будуть тут, коли з’являться в наявності.</p><button className="btn primary" onClick={()=>go('/catalog')}>ОБРАТИ АРОМАТ</button></div>}</div></main>
}
function Brands({ groups, go, setQuery }) {
  const brands=[...new Set([...featuredReference.map(x=>x[0]), ...groups.map(x=>x.brand)].filter(Boolean))]
  return <main><PageTitle label="АРОМАТИ З ХАРАКТЕРОМ" title="Бренди" detail="Добірка нішевих парфумерних будинків у нашому каталозі."/><section className="shell brand-grid">{brands.map(brand=><button key={brand} onClick={()=>{setQuery(brand);go('/catalog')}}><span>{brand}</span><Icon name="arrow" size={17}/></button>)}</section></main>
}
function Blog() {
  return <main><PageTitle label="НОТАТКИ ПРО АРОМАТИ" title="Блог" detail="Короткі поради, щоб знайомитися з парфумерією не поспішаючи."/><section className="shell stories"><article><p className="eyebrow">ГІД ПО АРОМАТАХ</p><h2>Чому одного пшика недостатньо?</h2><p>Аромат розкривається впродовж дня, реагує на температуру й шкіру та може звучати зовсім інакше, ніж на паперовому блотері. Малий об’єм допомагає прожити з ним кілька днів до рішення про великий флакон.</p></article><article><p className="eyebrow">ФОРМАТИ</p><h2>2, 5 чи 10 мл: з чого почати</h2><p>2 мл — для першого знайомства, 5 мл — щоб перевірити аромат у різних обставинах, 10 мл — для подорожі або улюбленого запаху поруч.</p></article></section></main>
}
function InfoModal({ name, close }) {
  const content = {
    delivery:['Доставка й оплата', 'Замовлення оформлюється безпосередньо на сайті. Доставка Новою поштою: у відділення, поштомат або кур’єром (за доступності). Оплата при отриманні або за погодженими реквізитами після підтвердження менеджером. Вартість доставки — за тарифами перевізника. Онлайн-еквайринг ще не підключений.'],
    returns:['Повернення', 'До відправлення замовлення можна скасувати у профілі, поки воно перебуває у дозволеному статусі. Умови повернення й обміну парфумерії визначаються законодавством та характером товару. Продавець має опублікувати повні реквізити, умови повернення й контакти до комерційного запуску.'],
    about:['Про ACCORD NICHE', 'ACCORD NICHE — сервіс розпиву оригінальної нішевої парфумерії. Принцип бренду: спробувати аромат у житті, перш ніж обирати повний флакон.'],
  }
  if (!name) return null
  return <div className="modal-mask" role="presentation" onMouseDown={e=>{if(e.currentTarget===e.target)close()}}><section className="info-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><button className="icon-btn modal-close" onClick={close} aria-label="Закрити"><Icon name="close"/></button><p className="eyebrow">ACCORD NICHE</p><h2 id="modal-title">{content[name]?.[0]}</h2><p>{content[name]?.[1]}</p><button className="btn outline" onClick={close}>Зрозуміло</button></section></div>
}

export default function App() {
  const [route,go] = useRoute()
  const commerce = useCommerce()
  const [orderResult,setOrderResult] = useState(null)
  const [products,setProducts]=useState([])
  const [site,setSite]=useState({})
  const [loading,setLoading]=useState(true)
  const [catalogLoaded,setCatalogLoaded]=useState(false)
  const [error,setError]=useState('')
  const [query,setQuery]=useState('')
  const [basketOpen,setBasketOpen]=useState(false)
  const [info,setInfo]=useState('')
  const [cart,setCart]=useState(()=>{try {
    const saved = JSON.parse(localStorage.getItem('accord:niche:cart')||'{}')
    return saved && typeof saved==='object' && !Array.isArray(saved) ? saved : {}
  }catch{return {}}})
  useEffect(()=>{try{localStorage.setItem('accord:niche:cart',JSON.stringify(cart))}catch{/* private browsing / quota */}},[cart])
  useEffect(()=>{if(catalogLoaded)setCart(prev=>sanitizeCart(prev,products))},[catalogLoaded,products])
  useEffect(()=>{fetch('/api/public/site-config').then(r=>r.ok?r.json():{}).then(setSite).catch(()=>{})},[])
  useEffect(()=>{
    let cancelled=false
    async function read(){
      setLoading(true); setError('')
      try {
        const all=[]
        for(let offset=0; offset<2000; offset+=100){
          const response=await fetch(`${PUBLIC_CATALOG}?limit=100&offset=${offset}`,{cache:'no-store'})
          if(!response.ok)throw new Error(`HTTP ${response.status}`)
          const page=await response.json()
          if(!Array.isArray(page.items))throw new Error('Некоректна відповідь API')
          all.push(...page.items)
          if(all.length>=page.total || page.items.length===0)break
        }
        if(!cancelled) {setProducts(all);setCatalogLoaded(true)}
      } catch(err){if(!cancelled)setError(err.message||'Недоступний API')}
      finally {if(!cancelled)setLoading(false)}
    }
    read()
    const timer=window.setInterval(()=>{if(!document.hidden)read()},60000)
    return ()=>{cancelled=true;window.clearInterval(timer)}
  },[])
  const groups=useMemo(()=>groupProducts(products),[products])
  const count=Object.values(cart).reduce((n,qty)=>n+Number(qty||0),0)
  const change=(id,qty)=>setCart(prev=>{const next={...prev};const p=products.find(p=>p.id===id);const number=Math.min(Math.max(0,qty),p?.stock||0,99);if(number)next[id]=number;else delete next[id];return next})
  const add=(p)=>{setCart(prev=>{
    const next={...prev};const qty=Math.min(Math.max(0,Number(prev[p.id])||0)+1,p.stock||0,99)
    if(qty)next[p.id]=qty;else delete next[p.id]
    return next
  });setBasketOpen(true)}
  const detail=route.match(/^\/aroma\/(\d+)$/)
  const group=detail ? groups.find(g=>g.variants.some(v=>v.id===Number(detail[1]))) : null
  return <>
    <Header go={go} query={query} setQuery={setQuery} count={count} onCart={()=>setBasketOpen(true)} account={commerce.account}/>
    {route==='/' ? <main><Hero go={go}/><HowItWorks/><Featured groups={groups} go={go}/><Authenticity/></main>
      : route==='/catalog' ? <Catalog groups={groups} go={go} query={query} setQuery={setQuery} error={error} loading={loading} />
      : route==='/sets' ? <Sets groups={groups} go={go}/>
      : route==='/brands' ? <Brands groups={groups} go={go} setQuery={setQuery}/>
      : route==='/how' ? <main><PageTitle label="ПРОСТО І ПРОЗОРО" title="Як це працює"/><HowItWorks compact/><Authenticity/></main>
      : route==='/blog' ? <Blog/>
      : route==='/checkout' ? <CheckoutPage shop={commerce} cart={cart} products={products} go={go} complete={result=>{setOrderResult(result);setCart({})}}/>
      : route==='/profile' ? <ProfilePage shop={commerce} go={go}/>
      : route==='/order/success' ? <CheckoutSuccess result={orderResult} go={go}/>
      : detail ? <Detail group={group} add={add} go={go}/>
      : <main><PageTitle label="404" title="Сторінку не знайдено"/><div className="shell"><button className="btn primary" onClick={()=>go('/')}>На головну</button></div></main>}
    <Footer go={go} setInfo={setInfo} site={site}/>
    <Basket open={basketOpen} close={()=>setBasketOpen(false)} cart={cart} products={products} change={change} go={go} site={site}/>
    <InfoModal name={info} close={()=>setInfo('')}/>
  </>
}
