import { useCallback, useEffect, useRef, useState } from 'react'
import { StoreIcon } from '../StoreIcon'
import { Field } from '../fields'
import { mountDialog } from '../dialog'
import { backButton } from '../telegram'

// Бренди замість категорій: парфумерію шукають за брендом. Ряд брендів над
// каталогом і повний список із пошуком (брендів може бути багато).
function BrandCount({ brand }) {
  return Number.isFinite(brand.products_count) ? <span className="taxonomy-count" title="Усього товарів бренду, до пошуку та фільтра наявності" aria-label={`Усього товарів бренду: ${brand.products_count}`}>{brand.products_count}</span> : null
}

function BrandTile({ name, selected, onClick, brand, detail, icon = 'box' }) {
  return <button className="category-tile" aria-label={name} aria-pressed={selected} onClick={onClick}>
    <span className="category-tile-symbol"><StoreIcon name={icon} /></span>
    <span className="category-tile-name">{name}</span>
    <span className="category-tile-detail">{brand && <BrandCount brand={brand} />}{detail}</span>
    {selected && <span className="category-tile-check"><StoreIcon name="check" /></span>}
  </button>
}

function BrandPicker({ brands, active, onBrand, onClose }) {
  const ref = useRef(null)
  const [query, setQuery] = useState('')
  useEffect(() => mountDialog(ref.current, onClose), [onClose])
  useEffect(() => { backButton(onClose); return () => backButton(null) }, [onClose])
  const needle = query.trim().toLocaleLowerCase('uk')
  const shown = brands.filter((brand) => brand.name.toLocaleLowerCase('uk').includes(needle))
  const select = (value) => { onBrand(value); onClose() }
  return <div className="sheet-backdrop" onClick={onClose}>
    <section className="sheet category-sheet" ref={ref} role="dialog" aria-modal="true" aria-labelledby="brand-picker-title" tabIndex={-1} onClick={(event) => event.stopPropagation()}>
      <div className="category-sheet-head"><div><p className="taxonomy-eyebrow">Оберіть парфумерний дім</p><h2 id="brand-picker-title">Усі бренди</h2></div><button className="store-icon-button" onClick={onClose} aria-label="Закрити бренди"><StoreIcon name="close" /></button></div>
      <div className="field category-search"><Field value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Назва бренду" aria-label="Пошук брендів" inputMode="search" /></div>
      {!needle && <div className="category-quick-actions"><button aria-pressed={active === null} onClick={() => select(null)}><StoreIcon name="catalog" />Усі аромати</button></div>}
      <div className="category-tree brand-list">
        {shown.map((brand) => <button key={brand.id} className="category-tree-root" aria-label={brand.name} aria-pressed={active === brand.id} onClick={() => select(brand.id)}><StoreIcon name="box" /><span>{brand.name}</span><BrandCount brand={brand} />{active === brand.id && <StoreIcon name="check" />}</button>)}
        {!shown.length && <p className="category-search-empty" role="status">Брендів за цим запитом немає. Спробуйте іншу назву.</p>}
      </div>
    </section>
  </div>
}

export function BrandNavigator({ brands, active, onBrand }) {
  const [open, setOpen] = useState(false)
  const [scroll, setScroll] = useState({ before: false, after: false })
  const railRef = useRef(null)
  const close = useCallback(() => setOpen(false), [])
  useEffect(() => {
    const rail = railRef.current
    const measure = () => setScroll({ before: rail.scrollLeft > 2, after: rail.scrollLeft + rail.clientWidth < rail.scrollWidth - 2 })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(rail)
    rail.addEventListener('scroll', measure, { passive: true })
    return () => { observer.disconnect(); rail.removeEventListener('scroll', measure) }
  }, [brands])
  useEffect(() => {
    // Reveal the selection horizontally without moving the page vertically.
    const rail = railRef.current
    const selected = rail?.querySelector('[aria-pressed="true"]')
    if (!selected) return
    const box = selected.getBoundingClientRect(), viewport = rail.getBoundingClientRect()
    if (box.left < viewport.left) rail.scrollLeft -= viewport.left - box.left + 16
    else if (box.right > viewport.right) rail.scrollLeft += box.right - viewport.right + 16
  }, [active, brands])
  const move = (direction) => railRef.current?.scrollBy({ left: direction * railRef.current.clientWidth * .75, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  const current = brands.find((brand) => brand.id === active)
  return <div className="catalog-taxonomy">
    <div className="taxonomy-heading"><h2>Бренди</h2><div className="taxonomy-heading-actions">{(scroll.before || scroll.after) && <div className="taxonomy-scroll-buttons"><button className="store-icon-button" aria-label="Попередні бренди" disabled={!scroll.before} onClick={() => move(-1)}><StoreIcon name="back" /></button><button className="store-icon-button" aria-label="Наступні бренди" disabled={!scroll.after} onClick={() => move(1)}><StoreIcon name="forward" /></button></div>}<button className="taxonomy-browse" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}>Усі бренди<StoreIcon name="catalog" /></button></div></div>
    <div ref={railRef} className="rail store-categories" role="group" aria-label="Бренди" tabIndex={0}>
      <BrandTile name="Усі" icon="catalog" selected={active === null} onClick={() => onBrand(null)} detail="Усі аромати" />
      {brands.map((brand) => <BrandTile key={brand.id} name={brand.name} brand={brand} selected={active === brand.id} onClick={() => onBrand(brand.id)} detail={brand.products_count === 0 ? 'Незабаром' : 'ароматів'} />)}
    </div>
    {current && <nav className="taxonomy-breadcrumb" aria-label="Обраний бренд"><button onClick={() => onBrand(null)}>Усі аромати</button><StoreIcon name="forward" /><span aria-current="page">{current.name}</span></nav>}
    {open && <BrandPicker brands={brands} active={active} onBrand={onBrand} onClose={close} />}
  </div>
}
