import { useEffect, useState } from 'react'
import { genderName } from '../catalog'
import { ProductSection } from './ProductCard'
import { money } from '../format'
import { ImageTile } from '../ui/ImageTile'
import { RequestStatus } from '../ui/RequestStatus'
import { useStoreRequest } from '../useStoreRequest'

export function Detail({id, go, add}) {
  const request = useStoreRequest('/api/public/aromas/' + id)
  const group = request.data?.item
  const [sku, setSku] = useState(id)
  useEffect(() => {
    if (group) setSku(group.variants.find(product => product.id === id)?.id || group.id)
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
  return <main><div className="shell detail-back"><button onClick={() => go('/catalog')}>← Усі аромати</button></div><div className="shell"><RequestStatus request={request}/></div>
    {group && current && <><section className="shell detail-grid"><ImageTile item={{...current, image: current.photo_url || current.photo_endpoint || group.image, brand:group.brand}} priority/><div className="detail-text"><p className="eyebrow">{group.brand}</p><h1>{group.name}</h1><p className="detail-kind">{genderName[group.gender] || 'унісекс'}</p>
      {group.bestseller_rank && group.bestseller_rank <= 8 && <p className="detail-hit">Хіт продажів · за останні 90 днів</p>}{group.description && <p className="detail-description">{group.description}</p>}
      <div className="variant-group"><h2 id="variant-title">Оберіть об’єм</h2><div className="variant-buttons" role="group" aria-labelledby="variant-title">{group.variants.map(product => <button key={product.id} aria-pressed={current.id === product.id} className={current.id === product.id ? 'selected' : ''} onClick={() => {setSku(product.id);go('/aroma/'+product.id, {replace:true, scroll:false})}}><span>{product.volume_ml ? product.volume_ml + ' мл' : product.name}</span><small>{product.stock > 0 ? money(product.price) : 'Немає'}</small></button>)}</div></div>
      <div className="detail-buy"><div><span>{current.volume_ml ? 'ЦІНА ЗА ' + current.volume_ml + ' МЛ' : 'ЦІНА'}</span>{current.is_sale && current.old_price && <del>{money(current.old_price)}</del>}<strong>{money(current.price)}</strong>{current.volume_ml > 0 && <p>{money(Number(current.price) / current.volume_ml)} / мл</p>}<p className={'detail-stock' + (current.stock > 0 ? ' in-stock' : '')}>{current.stock > 0 ? 'У наявності' : 'Немає в наявності'}</p></div><button className="btn primary" disabled={current.stock <= 0} onClick={() => add({...current, brand:group.brand})}>{current.stock > 0 ? 'ДОДАТИ В КОШИК' : 'НЕМАЄ В НАЯВНОСТІ'}</button></div><p className="microcopy">Ціна й наявність перевіряються повторно під час оформлення.</p></div></section>
      <ProductSection title="Схожі аромати" items={request.data.related} go={go}/></>}</main>
}
