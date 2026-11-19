import { useEffect, useState } from 'react'
import { ProductCard } from './ProductCard'
import { PageTitle } from '../ui/PageTitle'
import { RequestStatus } from '../ui/RequestStatus'
import { useStoreRequest } from '../useStoreRequest'

export function Catalog({route, go, sets = false}) {
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
  const [filtersOpen, setFiltersOpen] = useState(false)
  // W-18: every applied filter as a removable chip; removing one keeps the
  // rest and returns to page 1 (update() drops the page parameter).
  const genders = {female:'Жіночий', male:'Чоловічий', unisex:'Унісекс'}
  const chips = [
    params.get('q') && {key:'q', label:'Пошук: «' + params.get('q') + '»'},
    params.get('brand') && {key:'brand', label:'Бренд: ' + params.get('brand')},
    params.get('category') && {key:'category', label:'Категорія: ' + params.get('category')},
    params.get('gender') && {key:'gender', label:'Аромат для: ' + (genders[params.get('gender')] || params.get('gender'))},
    params.get('volume') && {key:'volume', label:params.get('volume') + ' мл'},
    params.get('available') === 'true' && {key:'available', label:'Лише в наявності'},
  ].filter(Boolean)
  const refineCount = chips.filter(chip => chip.key !== 'q').length
  const pages = Math.ceil((data?.total || 0) / 24)
  return <main><PageTitle label="КОЛЕКЦІЯ АРОМАТІВ" title={titles[kind] || 'Каталог'} detail={kind === 'hits' ? 'Добірка за фактичними продажами за останні 90 днів. Нові, скасовані та повернені замовлення не впливають на рейтинг.' : 'Актуальні ціни, доступні об’єми та наявність.'}/>
    <section className="shell catalog-layout" aria-label="Каталог ароматів"><div className="catalog-filters">
      <label>ПОШУК<input type="search" maxLength={120} value={search} onChange={event => {setSearch(event.target.value); setTyping(true)}} placeholder="Назва, бренд…"/></label>
      <label>СОРТУВАННЯ<select value={params.get('sort') || 'recommended'} onChange={event => update('sort', event.target.value)}><option value="recommended">Рекомендовані</option><option value="popular">За продажами</option><option value="new">Спочатку новинки</option><option value="price_asc">Спочатку дешевші</option><option value="price_desc">Спочатку дорожчі</option><option value="name">За назвою</option></select></label>
      {/* W-06: on a phone the refining filters fold behind one button with a count; on a wide screen they stay in the column. */}
      <button type="button" className="catalog-filters-toggle" aria-expanded={filtersOpen} aria-controls="catalog-filter-panel" onClick={() => setFiltersOpen(open => !open)}>Фільтри{refineCount ? ` (${refineCount})` : ''}</button>
      <div className={'catalog-filter-panel' + (filtersOpen ? ' is-open' : '')} id="catalog-filter-panel">
      <label>БРЕНД<select value={params.get('brand') || ''} onChange={event => update('brand', event.target.value)}><option value="">Усі бренди</option>{(data?.brands || facets.brands).map(brand => <option key={brand}>{brand}</option>)}</select></label>
      <label>КАТЕГОРІЯ<select value={params.get('category') || ''} onChange={event => update('category', event.target.value)}><option value="">Усі категорії</option>{(data?.categories || facets.categories).map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label>АРОМАТ ДЛЯ<select value={params.get('gender') || ''} onChange={event => update('gender', event.target.value)}><option value="">Для всіх</option><option value="female">Жіночий</option><option value="male">Чоловічий</option><option value="unisex">Унісекс</option></select></label>
      <label>ОБ’ЄМ<select value={params.get('volume') || ''} onChange={event => update('volume', event.target.value)}><option value="">Усі об’єми</option>{(data?.volumes || facets.volumes).map(volume => <option key={volume} value={volume}>{volume} мл</option>)}</select></label>
      <label className="stock-filter"><input type="checkbox" checked={params.get('available') === 'true'} onChange={event => update('available', event.target.checked ? 'true' : '')}/>Лише в наявності</label>
      <button className="filter-reset" onClick={() => go(sets ? '/sets' : '/catalog')}>Скинути фільтри</button></div></div>
      <div className="catalog-results" aria-busy={request.loading}>{chips.length > 0 && <div className="catalog-chips" role="group" aria-label="Застосовані фільтри">{chips.map(chip => <button type="button" key={chip.key} className="catalog-chip" aria-label={'Прибрати фільтр: ' + chip.label} onClick={() => {if (chip.key === 'q') setSearch(''); update(chip.key, '')}}><span>{chip.label}</span><span aria-hidden="true">×</span></button>)}{chips.length > 1 && <button type="button" className="catalog-chip clear" onClick={() => {setSearch(''); go(sets ? '/sets' : '/catalog')}}>Очистити все</button>}</div>}<div className="catalog-summary"><span>{data ? 'Знайдено ароматів: ' + data.total : 'Завантаження…'}</span>{request.loading && data && <span>Оновлюємо…</span>}</div>
        <RequestStatus request={request}>{data && !data.items.length ? <div className="store-state"><h2>{kind === 'hits' ? 'Хіти ще формуються' : 'Нічого не знайдено'}</h2><p>{kind === 'hits' ? 'Тут з’являться аромати з підтвердженими продажами.' : 'Спробуйте інший пошук або скинь фільтри.'}</p><button className="btn outline" onClick={() => go('/catalog')}>Весь каталог</button></div> : <div className="products-grid">{data?.items.map(item => <ProductCard key={item.key} item={item} go={go}/>)}</div>}</RequestStatus>
        {pages > 1 && <nav className="catalog-pagination" aria-label="Сторінки каталогу"><button className="btn outline" disabled={page <= 1} onClick={() => update('page', String(page - 1))}>← Назад</button><span>{page} / {pages}</span><button className="btn outline" disabled={page >= pages} onClick={() => update('page', String(page + 1))}>Далі →</button></nav>}
      </div></section></main>
}
