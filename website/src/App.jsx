import { useEffect, useState } from 'react'
import { genderName, sanitizeCart, telegramCheckoutUrl } from './catalog'
import { useStoreRequest } from './useStoreRequest'
import { useCommerce, CheckoutPage, CheckoutSuccess, ProfilePage } from './commerce'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const fmt = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 2 })
const money = value => fmt.format(Number(value)) + ' грн'

function useRoute() {
  const read = () => (location.pathname.slice(BASE.length) || '/') + location.search
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const pop = () => setRoute(read())
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])
  function go(to) {
    const next = BASE + to
    if (location.pathname + location.search !== next) history.pushState(null, '', next)
    setRoute(to)
    window.scrollTo({top: 0, behavior: 'instant'})
  }
  return [route, go]
}

function Icon({name, size = 21}) {
  const props = {width:size, height:size, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', strokeWidth:1.5, strokeLinecap:'round', strokeLinejoin:'round', 'aria-hidden':true}
  if (name === 'search') return <svg {...props}><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></svg>
  if (name === 'user') return <svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4.5 21c0-4 3.2-6 7.5-6s7.5 2 7.5 6"/></svg>
  if (name === 'bag') return <svg {...props}><path d="M4 8h16l-1.2 13H5.2L4 8Z"/><path d="M9 9V6a3 3 0 0 1 6 0v3"/></svg>
  if (name === 'close') return <svg {...props}><path d="m5 5 14 14M19 5 5 19"/></svg>
  if (name === 'menu') return <svg {...props}><path d="M3 7h18M3 12h18M3 17h18"/></svg>
  return <svg {...props}><path d="M4 12h16m-7-7 7 7-7 7"/></svg>
}

function Logo({dark = false, onClick}) {
  return <button className={'brandmark' + (dark ? ' inverse' : '')} onClick={onClick} aria-label="ACCORD NICHE — на головну"><strong>ACCORD</strong><span className="brandmark-bottom"><i/>NICHE<i/></span></button>
}

function Header({go, onCart, count, account}) {
  const [search, setSearch] = useState(false)
  const [query, setQuery] = useState('')
  const [menu, setMenu] = useState(false)
  const nav = [['/catalog','Каталог'],['/catalog?kind=hits','Хіти'],['/catalog?kind=new','Новинки'],['/sets','Набори'],['/brands','Бренди']]
  function navigate(path) {go(path); setMenu(false); setSearch(false)}
  return <header className="header"><div className="shell header-inner"><Logo onClick={() => navigate('/')}/>
    <nav className={'header-nav' + (menu ? ' open' : '')} aria-label="Головна навігація">{nav.map(([path,label]) => <button key={path} onClick={() => navigate(path)}>{label}</button>)}</nav>
    <div className="header-actions"><button className="icon-btn" aria-label="Профіль" title={account?.signed_in ? 'Мій профіль' : 'Увійти'} onClick={() => navigate('/profile')}><Icon name="user"/></button>
      <button className="icon-btn" aria-label="Пошук" onClick={() => setSearch(value => !value)}><Icon name="search"/></button>
      <button className="icon-btn cart-button" aria-label={'Кошик, товарів ' + count} onClick={onCart}><Icon name="bag"/>{count > 0 && <span className="cart-count">{count}</span>}</button>
      <button className="icon-btn menu-btn" aria-label="Меню" aria-expanded={menu} onClick={() => setMenu(value => !value)}><Icon name={menu ? 'close' : 'menu'}/></button></div></div>
    {search && <form className="search-strip shell" role="search" onSubmit={event => {event.preventDefault(); navigate('/catalog?q=' + encodeURIComponent(query.trim()))}}><Icon name="search"/><input aria-label="Знайти аромат або бренд" autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Знайти аромат або бренд…"/><button className="text-action" type="submit">Знайти →</button></form>}
  </header>
}

function ImageTile({item, className = '', priority = false}) {
  const source = item?.image || item?.photo_url || item?.photo_endpoint || ''
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [source])
  return <div className={'photo-tile ' + className}>{source && !failed
    ? <img loading={priority ? 'eager' : 'lazy'} decoding="async" src={source} alt={[item.brand,item.name].filter(Boolean).join(' ')} referrerPolicy="no-referrer" onError={() => setFailed(true)}/>
    : <div className="image-unavailable"><svg viewBox="0 0 80 100" fill="none" aria-hidden="true"><path d="M29 7h22v16H29zM34 23h12v12H34zM21 35h38v55H21zM28 48h24v24H28z" stroke="currentColor" strokeWidth="1.2"/></svg><span>Зображення недоступне</span></div>}</div>
}

function RequestStatus({request, empty, children}) {
  if (!request.data && request.loading) return <div className="store-loading" role="status"><span className="loading-dot"/>Завантажуємо товари…</div>
  if (!request.data && request.error) return <div className="store-state" role="alert"><h2>Магазин тимчасово недоступний</h2><p>{request.error}</p><button className="btn outline" onClick={request.retry}>Спробувати ще раз</button></div>
  return <>{request.error && <div className="notice" role="alert">Не вдалося оновити дані. Показуємо останню завантажену версію. <button onClick={request.retry}>Оновити</button></div>}{empty ? <div className="store-state"><h2>Поки немає товарів</h2><p>Перегляньте інші добірки або завітайте пізніше.</p></div> : children}</>
}

function ProductCard({item, go}) {
  const hit = item.bestseller_rank > 0 && item.bestseller_rank <= 8
  return <article className="product-card available"><button className="product-link" onClick={() => go('/aroma/' + item.id)} aria-label={[item.brand,item.name,'— переглянути'].filter(Boolean).join(' ')}>
    <div className="product-visual"><ImageTile item={item}/><div className="product-badges">{item.stock <= 0 ? <span>Немає в наявності</span> : <>{hit && <span className="hit-badge">Хіт продажів</span>}{item.is_new && <span>Новинка</span>}</>}</div></div>
    <div className="product-meta">{item.brand && <span className="product-brand">{item.brand}</span>}<h3>{item.name}</h3><p>{genderName[item.gender] || 'унісекс'}{item.volumes?.length > 0 ? ' · ' + item.volumes.join(' / ') + ' мл' : ''}</p>
      <strong>від {money(item.min_price)}</strong>{item.price_per_ml != null && <span className="unit-price">від {money(item.price_per_ml)} / мл</span>}
      <span className={'availability ' + (item.stock > 0 ? 'in-stock' : '')}>{item.stock > 0 ? 'У наявності' : 'Тимчасово відсутній'}</span></div>
  </button></article>
}

function ProductSection({title, description, items, go, to = '/catalog'}) {
  if (!items?.length) return null
  return <section className="featured shell"><div className="section-row"><div><h2 className="section-heading">{title}</h2>{description && <p className="section-description">{description}</p>}</div><button className="section-link" onClick={() => go(to)}>ПЕРЕГЛЯНУТИ ВСІ →</button></div><div className="products-grid">{items.map(item => <ProductCard key={item.key} item={item} go={go}/>)}</div></section>
}

function Hero({go, item}) {
  return <section className="hero shell" aria-labelledby="hero-title"><div className="hero-content"><p className="eyebrow">НІШЕВА ПАРФУМЕРІЯ У ТВОЄМУ ФОРМАТІ</p><h1 id="hero-title">Знайди аромат,<br/>який стане<br/>твоїм</h1><p className="hero-description">Обирай аромат і доступний об’єм. Знайомся з парфумерією у власному ритмі — перед рішенням про повний флакон.</p><div className="hero-cta"><button className="btn primary" onClick={() => go('/catalog')}>ОБРАТИ АРОМАТ</button><button className="btn outline" onClick={() => go('/catalog?kind=new')}>НОВИНКИ</button></div></div>
    {item?.image ? <button className="hero-product" onClick={() => go('/aroma/' + item.id)}><ImageTile item={item} className="hero-tile" priority/><span>{item.brand} · {item.name}</span></button> : <div className="hero-lettering" aria-hidden="true"><span>A</span><p>ACCORD NICHE</p><i>Твій аромат. Твій формат.</i></div>}</section>
}

function HowItWorks() {
  return <section className="how-section"><div className="shell"><h2 className="section-heading light">Як це працює</h2><div className="steps"><article><span className="step-number">01</span><h3>Обираєш аромат</h3><p>Порівнюй бренди, доступні об’єми та ціни за мілілітр.</p></article><article><span className="step-number">02</span><h3>Оформлюєш замовлення</h3><p>Додавай потрібний об’єм у кошик і обирай спосіб доставки.</p></article><article><span className="step-number">03</span><h3>Стежиш за доставкою</h3><p>Історія замовлень і актуальний статус доступні в особистому кабінеті.</p></article></div></div></section>
}

function Home({go}) {
  const request = useStoreRequest('/api/public/storefront')
  const data = request.data
  return <main><Hero go={go} item={data?.selection?.[0]}/><div className="shell"><RequestStatus request={request} empty={data?.total === 0}/></div>
    {data && <>{data.hits.length > 0 ? <ProductSection title="Хіти розливу" description={'Найпопулярніші за підтвердженими продажами за ' + data.window_days + ' днів.'} items={data.hits} go={go} to="/catalog?kind=hits"/> : <ProductSection title="Обери свій аромат" description="Товари з актуального каталогу магазину." items={data.selection} go={go}/>}
      <ProductSection title="Новинки" items={data.new_arrivals} go={go} to="/catalog?kind=new"/><ProductSection title="Рекомендуємо" description="Добірка магазину для знайомства з ароматами." items={data.recommended} go={go} to="/catalog?kind=recommended"/></>}<HowItWorks/></main>
}

function PageTitle({label, title, detail}) {
  return <div className="page-title shell"><p className="eyebrow">{label}</p><h1>{title}</h1>{detail && <p>{detail}</p>}</div>
}

function Catalog({route, go, sets = false}) {
  const params = new URLSearchParams(route.split('?')[1] || '')
  const kind = sets ? 'sets' : params.get('kind') || 'all'
  const [search, setSearch] = useState(params.get('q') || '')
  const [typing, setTyping] = useState(false)
  useEffect(() => {setSearch(params.get('q') || ''); setTyping(false)}, [route])
  function update(key, value) {
    const next = new URLSearchParams(route.split('?')[1] || '')
    if (value) next.set(key, value); else next.delete(key)
    if (key !== 'page') next.delete('page')
    go((sets ? '/sets' : '/catalog') + (next.size ? '?' + next : ''))
  }
  useEffect(() => {
    if (!typing) return
    const timer = setTimeout(() => update('q', search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search, typing])
  const page = Math.max(1, Number.parseInt(params.get('page') || '1', 10) || 1)
  const apiParams = new URLSearchParams(params)
  apiParams.delete('page')
  apiParams.set('kind', kind)
  apiParams.set('limit', '24')
  apiParams.set('offset', String((page - 1) * 24))
  const request = useStoreRequest('/api/public/aromas?' + apiParams)
  const data = request.data
  const [facets, setFacets] = useState({brands:[], categories:[], volumes:[]})
  useEffect(() => {
    if (data) setFacets({brands:data.brands, categories:data.categories, volumes:data.volumes || []})
  }, [data])
  const titles = {all:'Каталог',hits:'Хіти продажів',new:'Новинки',recommended:'Рекомендуємо',sets:'Набори пробників'}
  const pages = Math.ceil((data?.total || 0) / 24)
  return <main><PageTitle label="КОЛЕКЦІЯ АРОМАТІВ" title={titles[kind] || 'Каталог'} detail={kind === 'hits' ? 'Добірка за фактичними продажами за останні 90 днів. Нові, скасовані та повернені замовлення не впливають на рейтинг.' : 'Актуальні ціни, доступні об’єми та наявність.'}/>
    <section className="shell catalog-layout" aria-label="Каталог ароматів"><div className="catalog-filters">
      <label>ПОШУК<input value={search} onChange={event => {setSearch(event.target.value); setTyping(true)}} placeholder="Назва, бренд…"/></label>
      <label>БРЕНД<select value={params.get('brand') || ''} onChange={event => update('brand', event.target.value)}><option value="">Усі бренди</option>{(data?.brands || facets.brands).map(brand => <option key={brand}>{brand}</option>)}</select></label>
      <label>КАТЕГОРІЯ<select value={params.get('category') || ''} onChange={event => update('category', event.target.value)}><option value="">Усі категорії</option>{(data?.categories || facets.categories).map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label>АРОМАТ ДЛЯ<select value={params.get('gender') || ''} onChange={event => update('gender', event.target.value)}><option value="">Для всіх</option><option value="female">Жіночий</option><option value="male">Чоловічий</option><option value="unisex">Унісекс</option></select></label>
      <label>ОБ’ЄМ<select value={params.get('volume') || ''} onChange={event => update('volume', event.target.value)}><option value="">Усі об’єми</option>{(data?.volumes || facets.volumes).map(volume => <option key={volume} value={volume}>{volume} мл</option>)}</select></label>
      <label>СОРТУВАННЯ<select value={params.get('sort') || 'recommended'} onChange={event => update('sort', event.target.value)}><option value="recommended">Рекомендовані</option><option value="popular">За продажами</option><option value="new">Спочатку новинки</option><option value="price_asc">Спочатку дешевші</option><option value="price_desc">Спочатку дорожчі</option><option value="name">За назвою</option></select></label>
      <label className="stock-filter"><input type="checkbox" checked={params.get('available') === 'true'} onChange={event => update('available', event.target.checked ? 'true' : '')}/>Лише в наявності</label>
      <button className="filter-reset" onClick={() => go(sets ? '/sets' : '/catalog')}>Скинути фільтри</button></div>
      <div className="catalog-results" aria-busy={request.loading}><div className="catalog-summary"><span>{data ? 'Знайдено ароматів: ' + data.total : 'Завантаження…'}</span>{request.loading && data && <span>Оновлюємо…</span>}</div>
        <RequestStatus request={request}>{data && !data.items.length ? <div className="store-state"><h2>{kind === 'hits' ? 'Хіти ще формуються' : 'Нічого не знайдено'}</h2><p>{kind === 'hits' ? 'Тут з’являться аромати з підтвердженими продажами.' : 'Спробуй інший пошук або скинь фільтри.'}</p><button className="btn outline" onClick={() => go('/catalog')}>Весь каталог</button></div> : <div className="products-grid">{data?.items.map(item => <ProductCard key={item.key} item={item} go={go}/>)}</div>}</RequestStatus>
        {pages > 1 && <nav className="catalog-pagination" aria-label="Сторінки каталогу"><button className="btn outline" disabled={page <= 1} onClick={() => update('page', String(page - 1))}>← Назад</button><span>{page} / {pages}</span><button className="btn outline" disabled={page >= pages} onClick={() => update('page', String(page + 1))}>Далі →</button></nav>}
      </div></section></main>
}

function Detail({id, go, add}) {
  const request = useStoreRequest('/api/public/aromas/' + id)
  const group = request.data?.item
  const [sku, setSku] = useState(id)
  useEffect(() => {
    if (group) setSku(group.variants.find(product => product.id === id && product.stock > 0)?.id || group.variants.find(product => product.stock > 0)?.id || group.variants[0].id)
  }, [group?.id, id])
  const current = group?.variants.find(product => product.id === Number(sku)) || group?.variants[0]
  return <main><div className="shell detail-back"><button onClick={() => go('/catalog')}>← Усі аромати</button></div><div className="shell"><RequestStatus request={request}/></div>
    {group && current && <><section className="shell detail-grid"><ImageTile item={{...current, image: current.photo_url || current.photo_endpoint || group.image, brand:group.brand}} priority/><div className="detail-text"><p className="eyebrow">{group.brand}</p><h1>{group.name}</h1><p className="detail-kind">{genderName[group.gender] || 'унісекс'}</p>
      {group.bestseller_rank && group.bestseller_rank <= 8 && <p className="detail-hit">Хіт продажів · за останні 90 днів</p>}{group.description && <p className="detail-description">{group.description}</p>}
      <div className="variant-group"><h2>Обери об’єм</h2><div className="variant-buttons">{group.variants.map(product => <button key={product.id} disabled={product.stock <= 0} aria-pressed={current.id === product.id} className={current.id === product.id ? 'selected' : ''} onClick={() => setSku(product.id)}>{product.volume_ml ? product.volume_ml + ' мл' : product.name}{product.stock <= 0 && <small>Немає</small>}</button>)}</div></div>
      <div className="detail-buy"><div><span>ЦІНА ЗА ОБРАНИЙ ОБ’ЄМ</span>{current.is_sale && current.old_price && <del>{money(current.old_price)}</del>}<strong>{money(current.price)}</strong>{current.volume_ml > 0 && <p>{money(Number(current.price) / current.volume_ml)} / мл</p>}</div><button className="btn primary" disabled={current.stock <= 0} onClick={() => add({...current, brand:group.brand})}>{current.stock > 0 ? 'ДОДАТИ В КОШИК' : 'НЕМАЄ В НАЯВНОСТІ'}</button></div><p className="microcopy">Ціна й наявність перевіряються повторно під час оформлення.</p></div></section>
      <ProductSection title="Схожі аромати" items={request.data.related} go={go}/></>}</main>
}

function Brands({go}) {
  const request = useStoreRequest('/api/public/aromas?limit=1')
  return <main><PageTitle label="ПАРФУМЕРНІ БУДИНКИ" title="Бренди" detail="Бренди, представлені в актуальному каталозі."/><section className="shell"><RequestStatus request={request} empty={request.data?.brands?.length === 0}><div className="brand-grid">{request.data?.brands.map(brand => <button key={brand} onClick={() => go('/catalog?brand=' + encodeURIComponent(brand))}><span>{brand}</span><Icon name="arrow" size={17}/></button>)}</div></RequestStatus></section></main>
}

function Guides() {
  return <main><PageTitle label="ЗНАЙОМСТВО З ПАРФУМЕРІЄЮ" title="Про аромати"/><section className="shell stories"><article><p className="eyebrow">ПЕРШЕ ЗНАЙОМСТВО</p><h2>Дай аромату час</h2><p>Спробуй аромат на шкірі й поспостерігай, як він розкривається протягом дня. Температура, погода та власне сприйняття впливають на враження.</p></article><article><p className="eyebrow">ТВІЙ ФОРМАТ</p><h2>Обирай зручний об’єм</h2><p>Невеликий об’єм підходить для першого знайомства, більший — для аромату, який уже став улюбленим. Доступні формати та їхні ціни вказані в картці кожного товару.</p></article></section></main>
}

function Basket({open, close, cart, products, change, go, site, request}) {
  useEffect(() => {
    if (!open) return
    const key = event => {if (event.key === 'Escape') close()}
    const old = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', key)
    return () => {document.body.style.overflow = old; window.removeEventListener('keydown', key)}
  }, [open])
  if (!open) return null
  const lines = Object.entries(cart).map(([id,qty]) => ({product:products.find(product => product.id === Number(id)), qty:Number(qty)})).filter(line => line.product)
  const total = lines.reduce((sum,line) => sum + Number(line.product.price) * line.qty, 0)
  const link = telegramCheckoutUrl(site.miniapp_url || '', cart, products)
  const blocked = Boolean(request.loading || request.error || Object.keys(cart).length !== lines.length)
  return <div className="drawer-backdrop" onMouseDown={event => {if (event.target === event.currentTarget) close()}}><aside role="dialog" aria-modal="true" aria-label="Кошик" className="basket"><div className="basket-head"><h2>Кошик</h2><button className="icon-btn" aria-label="Закрити кошик" onClick={close}><Icon name="close"/></button></div>
    <div className="basket-lines">{Object.keys(cart).length > 0 && request.error && <div role="alert" className="notice">Не вдалося перевірити кошик. <button onClick={request.retry}>Спробувати ще раз</button></div>}{request.loading && <p role="status" className="shop-hint">Перевіряємо ціни й наявність…</p>}
      {lines.map(({product,qty}) => <div className="basket-line" key={product.id}><div className="basket-thumb"><ImageTile item={product}/></div><div className="basket-info"><h3>{product.brand && product.brand + ' · '}{product.name}</h3><p>{product.volume_ml ? product.volume_ml + ' мл' : ''}</p><strong>{money(Number(product.price) * qty)}</strong><div className="qty-control"><button aria-label="Зменшити кількість" onClick={() => change(product.id, qty - 1)}>−</button><span>{qty}</span><button aria-label="Збільшити кількість" disabled={qty >= product.stock || qty >= 99} onClick={() => change(product.id, qty + 1)}>+</button><button className="remove-btn" onClick={() => change(product.id, 0)}>Видалити</button></div></div></div>)}
      {!Object.keys(cart).length && <div className="empty-basket"><p>У кошику поки порожньо</p><button className="btn outline" onClick={() => {close(); go('/catalog')}}>Переглянути аромати</button></div>}</div>
    {lines.length > 0 && <div className="basket-bottom"><div className="basket-total"><span>Разом</span><strong>{money(total)}</strong></div><button className="btn primary checkout-link" disabled={blocked} onClick={() => {close(); go('/checkout')}}>ОФОРМИТИ ЗАМОВЛЕННЯ →</button>{link && <a className="basket-telegram-link" href={link} target="_blank" rel="noopener noreferrer">Продовжити в Telegram Mini App</a>}<p>Кошик зберігається на цьому пристрої. Остаточну суму розрахуємо під час оформлення.</p></div>}</aside></div>
}

function Footer({go, setInfo, site}) {
  return <footer className="footer"><div className="shell footer-inner"><div className="footer-brand"><Logo dark onClick={() => go('/')}/><span>accordniche.pp.ua</span>{site.seller_name && <span>{site.seller_name}</span>}</div><div className="footer-links"><div><button onClick={() => setInfo('delivery')}>Доставка й оплата</button><button onClick={() => setInfo('returns')}>Повернення</button><button onClick={() => go('/how')}>Як це працює</button><button onClick={() => go('/blog')}>Про аромати</button></div><div>{site.instagram_url && <a href={site.instagram_url} target="_blank" rel="noopener noreferrer">Instagram</a>}{site.tiktok_url && <a href={site.tiktok_url} target="_blank" rel="noopener noreferrer">TikTok</a>}{site.phone && <a href={'tel:' + site.phone.replace(/[^+\d]/g,'')}>{site.phone}</a>}{site.email && <a href={'mailto:' + site.email}>{site.email}</a>}</div></div></div></footer>
}

function InfoModal({name, close, site}) {
  const content = {delivery:['Доставка й оплата','Оформлюй замовлення на сайті, обирай доступний спосіб доставки та оплати. Підсумкова сума, знижки й умови показані перед підтвердженням. Статус і дані відправлення зберігаються в особистому кабінеті.'], returns:['Повернення та скасування','До відправлення замовлення можна скасувати в особистому кабінеті, якщо для його статусу доступне скасування. Із питаннями щодо отриманого товару звертайся до магазину за контактами нижче.']}
  if (!name) return null
  return <div className="modal-mask" onMouseDown={event => {if (event.target === event.currentTarget) close()}}><section className="info-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><button className="icon-btn modal-close" onClick={close} aria-label="Закрити"><Icon name="close"/></button><p className="eyebrow">ACCORD NICHE</p><h2 id="modal-title">{content[name]?.[0]}</h2><p>{content[name]?.[1]}</p>{site.phone && <p>{site.phone}</p>}{site.email && <p>{site.email}</p>}<button className="btn outline" onClick={close}>Зрозуміло</button></section></div>
}

export default function App() {
  const [route, go] = useRoute()
  const path = route.split('?')[0]
  const commerce = useCommerce()
  const [orderResult, setOrderResult] = useState(null)
  const [products, setProducts] = useState([])
  const [basketOpen, setBasketOpen] = useState(false)
  const [info, setInfo] = useState('')
  const [notice, setNotice] = useState('')
  const [cart, setCart] = useState(() => {try {
    const saved = JSON.parse(localStorage.getItem('accord:niche:cart') || '{}')
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? Object.fromEntries(Object.entries(saved).filter(([id,qty]) => /^[1-9][0-9]*$/.test(id) && Number.isSafeInteger(Number(id)) && Number.isInteger(Number(qty)) && Number(qty) > 0).slice(0,30)) : {}
  } catch {return {}}})
  const ids = Object.keys(cart).sort((a,b) => Number(a) - Number(b)).join(',')
  const cartRequest = useStoreRequest(ids ? '/api/public/products?ids=' + ids : null)
  const siteRequest = useStoreRequest('/api/public/site-config')
  const site = siteRequest.data || {}
  useEffect(() => {try {localStorage.setItem('accord:niche:cart', JSON.stringify(cart))} catch {}}, [cart])
  useEffect(() => {
    if (Array.isArray(cartRequest.data)) {
      setProducts(cartRequest.data)
      setCart(old => sanitizeCart(old, cartRequest.data))
    }
  }, [cartRequest.data])
  function change(id, qty) {
    setCart(old => {const next = {...old}; const product = products.find(product => product.id === id); const capped = Math.min(Math.max(0,qty), product?.stock || 0, 99); if (capped) next[id] = capped; else delete next[id]; return next})
  }
  function add(product) {
    if (!cart[product.id] && Object.keys(cart).length >= 30) {setNotice('У кошику може бути до 30 різних позицій.'); return}
    setProducts(old => [...old.filter(item => item.id !== product.id), product])
    setCart(old => ({...old, [product.id]: Math.min((Number(old[product.id]) || 0) + 1, product.stock, 99)}))
    setBasketOpen(true)
  }
  const detail = path.match(/^\/aroma\/(\d+)$/)
  const count = Object.values(cart).reduce((sum,qty) => sum + Number(qty), 0)
  return <><Header go={go} onCart={() => setBasketOpen(true)} count={count} account={commerce.account}/>
    {notice && <div className="shell notice" role="alert">{notice}<button onClick={() => setNotice('')}>Закрити</button></div>}
    {path === '/' ? <Home go={go}/> : path === '/catalog' || path === '/sets' ? <Catalog key={path} route={route} go={go} sets={path === '/sets'}/> : path === '/brands' ? <Brands go={go}/> : path === '/blog' ? <Guides/> : detail ? <Detail id={Number(detail[1])} go={go} add={add}/> : path === '/checkout' ? <>{cartRequest.error || (ids && !cartRequest.data) ? <main className="shell commerce-page"><RequestStatus request={cartRequest}/></main> : <CheckoutPage shop={commerce} cart={cart} products={products} go={go} complete={result => {setOrderResult(result); setCart({})}}/>}</> : path === '/profile' ? <ProfilePage shop={commerce} go={go}/> : path === '/order/success' ? <CheckoutSuccess result={orderResult} go={go}/> : path === '/how' ? <main><PageTitle label="ПРОСТО І ЗРОЗУМІЛО" title="Як це працює"/><HowItWorks/></main> : <main><PageTitle label="404" title="Сторінку не знайдено"/><div className="shell"><button className="btn outline" onClick={() => go('/')}>На головну</button></div></main>}
    <Footer go={go} setInfo={setInfo} site={site}/><Basket open={basketOpen} close={() => setBasketOpen(false)} cart={cart} products={products} change={change} go={go} site={site} request={cartRequest}/><InfoModal name={info} close={() => setInfo('')} site={site}/>
  </>
}
