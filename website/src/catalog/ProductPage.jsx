import { useEffect, useRef, useState } from 'react'
import { genderName } from '../catalog'
import { ProductSection } from './ProductCard'
import { money } from '../format'
import { ImageTile } from '../ui/ImageTile'
import { RequestStatus } from '../ui/RequestStatus'
import { useStoreRequest } from '../useStoreRequest'
import { AromaDetails, Breadcrumbs } from './AromaDetails'
import { aromaPath } from './aromaPath'

export function Detail({id, go, add}) {
  const request = useStoreRequest('/api/public/aromas/' + id)
  const group = request.data?.item
  const [sku, setSku] = useState(id)
  const picked = useRef(null)
  useEffect(() => {
    if (!group) return
    // The aroma address (first SKU) opens the best offer; a volume link opens that volume.
    const chosen = (id !== group.id || picked.current === id) && group.variants.find(product => product.id === id)
    setSku(chosen ? chosen.id : group.default_product_id || group.id)
    // Old /aroma/<id> links get the readable address without a new history entry.
    const wanted = chosen ? aromaPath(group, chosen.id) : group.path
    if (wanted && location.pathname.replace(/\/+$/, '').endsWith('/aroma/' + id) && !location.pathname.endsWith(wanted)) go(wanted + location.search, {replace: true, scroll: false})
  }, [group?.id, id])
  const current = group?.variants.find(product => product.id === Number(sku)) || group?.variants[0]
  // The server already sends this title on a direct visit (SSI); keep it in
  // step when the shopper arrives through in-app navigation.
  useEffect(() => {
    if (!group) return
    const previous = document.title
    document.title = [group.brand, group.name].filter(Boolean).join(' ') + ' — ACCORD NICHE'
    return () => { document.title = previous }
  }, [group?.id])
  const crumbs = group ? [['Головна', '/'], ['Каталог', '/catalog'], ...(group.brand ? [[group.brand, '/catalog?brand=' + encodeURIComponent(group.brand)]] : []), [group.name]] : []
  return <main>{group ? <Breadcrumbs items={crumbs} go={go}/> : <div className="shell detail-back"><button onClick={() => go('/catalog')}>← Усі аромати</button></div>}<div className="shell"><RequestStatus request={request}/></div>
    {group && current && <><section className="shell detail-grid"><ImageTile item={{...current, name: group.name, image: current.photo_url || current.photo_endpoint || group.image, brand:group.brand, image_alt: group.image_alt}} priority sizes="(max-width: 750px) 100vw, 50vw"/><div className="detail-text"><p className="eyebrow">{group.brand}</p><h1>{group.name}</h1><p className="detail-kind">{genderName[group.gender] || 'унісекс'}</p>
      {group.bestseller_rank && group.bestseller_rank <= 8 && <p className="detail-hit">Хіт продажів · за останні 90 днів</p>}{group.description && <p className="detail-description">{group.description}</p>}<AromaDetails group={group}/>
      <div className="variant-group"><h2 id="variant-title">Оберіть об’єм</h2><div className="variant-buttons" role="group" aria-labelledby="variant-title">{group.variants.map(product => <button key={product.id} aria-pressed={current.id === product.id} className={current.id === product.id ? 'selected' : ''} onClick={() => {picked.current = product.id;setSku(product.id);go(aromaPath(group, product.id), {replace:true, scroll:false})}}><span>{product.volume_ml ? product.volume_ml + ' мл' : product.name}</span><small>{product.stock > 0 ? money(product.price) : 'Немає'}</small></button>)}</div></div>
      <div className="detail-buy"><div><span>{current.volume_ml ? 'ЦІНА ЗА ' + current.volume_ml + ' МЛ' : 'ЦІНА'}</span>{current.is_sale && current.old_price && <del>{money(current.old_price)}</del>}<strong>{money(current.price)}</strong>{current.volume_ml > 0 && <p>{money(Number(current.price) / current.volume_ml)} / мл</p>}<p className={'detail-stock' + (current.stock > 0 ? ' in-stock' : '')}>{current.stock > 0 ? 'У наявності' : 'Немає в наявності'}</p></div><button className="btn primary" disabled={current.stock <= 0} onClick={() => add({...current, brand:group.brand})}>{current.stock > 0 ? 'ДОДАТИ В КОШИК' : 'НЕМАЄ В НАЯВНОСТІ'}</button></div><p className="microcopy">Ціна й наявність перевіряються повторно під час оформлення.</p></div></section>
      <ProductSection title="Схожі аромати" items={request.data.related} go={go}/></>}</main>
}
