import { useEffect, useRef, useState } from 'react'
import { SiteLink } from '../router'
import { Icon } from '../ui/Icon'

export function Logo({dark = false, onClick}) {
  return <SiteLink to="/" onNavigate={() => onClick()} className={'brandmark' + (dark ? ' inverse' : '')} aria-label="ACCORD NICHE — на головну"><strong>ACCORD</strong><span className="brandmark-bottom" data-decorative=""><i/>NICHE<i/></span></SiteLink>
}

// Which menu item is the page you are on. Catalog sections differ only by
// ?kind=, articles and products belong to their section.
export function activeNav(route) {
  const [path, search = ''] = route.split('?')
  const kind = new URLSearchParams(search).get('kind') || ''
  if (path === '/catalog') return kind === 'hits' ? '/catalog?kind=hits' : kind === 'new' ? '/catalog?kind=new' : '/catalog'
  if (path.startsWith('/aroma/')) return '/catalog'
  if (path === '/blog' || path.startsWith('/blog/')) return '/blog'
  return ['/sets', '/brands'].includes(path) ? path : ''
}

export function Header({go, onCart, onLogout, count, account, route}) {
  const [leaving, setLeaving] = useState(false)
  const [search, setSearch] = useState(false)
  const [query, setQuery] = useState('')
  const [menu, setMenu] = useState(false)
  const menuButton=useRef(null),searchButton=useRef(null)
  const previousRoute=useRef(route)
  useEffect(()=>{
    if(previousRoute.current!==route){previousRoute.current=route;setMenu(false);setSearch(false)}
  },[route])
  useEffect(()=>{
    if(!menu && !search)return
    const close=event=>{if(event.key==='Escape' && !document.querySelector('[aria-modal="true"]')){event.preventDefault();setMenu(false);setSearch(false);(search?searchButton:menuButton).current?.focus()}}
    document.addEventListener('keydown',close)
    return()=>document.removeEventListener('keydown',close)
  },[menu,search])
  const nav = [['/catalog','Каталог'],['/catalog?kind=hits','Хіти'],['/catalog?kind=new','Новинки'],['/sets','Набори'],['/brands','Бренди'],['/blog','Блог']]
  function navigate(path) {go(path); setMenu(false); setSearch(false)}
  return <header className="header"><div className="shell header-inner"><Logo onClick={() => navigate('/')}/>
    <nav className={'header-nav' + (menu ? ' open' : '')} id="store-navigation" aria-label="Головна навігація">{nav.map(([path,label]) => <SiteLink key={path} to={path} onNavigate={navigate} current={activeNav(route) === path}>{label}</SiteLink>)}
      {account?.signed_in && onLogout && <button type="button" className="nav-logout" disabled={leaving} onClick={async () => {setMenu(false);setLeaving(true);try {await onLogout()} finally {setLeaving(false)}}}>Вийти з профілю</button>}</nav>
    <div className="header-actions"><button className={'icon-btn' + (account?.signed_in ? ' signed-in' : '')} aria-label={account?.signed_in ? 'Мій профіль' : 'Увійти в профіль'} aria-current={route.split('?')[0] === '/profile' ? 'page' : undefined} title={account?.signed_in ? 'Мій профіль' : 'Увійти'} onClick={() => navigate('/profile')}><Icon name="user"/></button>
      <button className="icon-btn" ref={searchButton} aria-label="Пошук" aria-expanded={search} aria-controls="store-search" onClick={() => {setMenu(false);setSearch(value => !value)}}><Icon name="search"/></button>
      <button className="icon-btn cart-button" aria-label={'Кошик, товарів ' + count} onClick={()=>{setMenu(false);setSearch(false);onCart()}}><Icon name="bag"/>{count > 0 && <span className="cart-count" key={count}>{count}</span>}</button>
      {account?.signed_in && onLogout && <button className="icon-btn logout-btn" aria-label="Вийти з профілю" title="Вийти з профілю" disabled={leaving}
        onClick={async () => {setMenu(false);setSearch(false);setLeaving(true);try {await onLogout()} finally {setLeaving(false)}}}><Icon name="logout"/></button>}
      <button className="icon-btn menu-btn" ref={menuButton} aria-label="Меню" aria-expanded={menu} aria-controls="store-navigation" onClick={() => {setSearch(false);setMenu(value => !value)}}><Icon name={menu ? 'close' : 'menu'}/></button></div></div>
    {search && <form id="store-search" className="search-strip shell" role="search" onSubmit={event => {event.preventDefault(); navigate('/catalog?q=' + encodeURIComponent(query.trim()))}}><Icon name="search"/><input aria-label="Знайти аромат або бренд" maxLength={120} autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Знайти аромат або бренд…"/><button className="text-action" type="submit">Знайти →</button></form>}
  </header>
}
