import { genderName } from '../catalog'
import { money } from '../format'
import { SiteLink } from '../router'
import { ImageTile } from '../ui/ImageTile'
import { aromaPath } from './aromaPath'

export function ProductCard({item, go}) {
  const hit = item.bestseller_rank > 0 && item.bestseller_rank <= 8
  return <article className="product-card available"><SiteLink className="product-link" to={aromaPath(item)} onNavigate={go} aria-label={[item.brand,item.name,'— переглянути'].filter(Boolean).join(' ')}>
    <div className="product-visual"><ImageTile item={item}/><div className="product-badges">{item.stock <= 0 ? <span className="stock-badge">Немає в наявності</span> : <>{hit && <span className="hit-badge">Хіт продажів</span>}{item.is_new && <span>Новинка</span>}</>}</div></div>
    <div className="product-meta">{item.brand && <span className="product-brand">{item.brand}</span>}<h3>{item.name}</h3><p>{genderName[item.gender] || 'унісекс'}{item.volumes?.length > 0 ? ' · ' + item.volumes.join(' / ') + ' мл' : ''}</p>
      <strong>від {money(item.min_price)}</strong>{item.price_per_ml != null && <span className="unit-price">від {money(item.price_per_ml)} / мл</span>}
      <span className={'availability ' + (item.stock > 0 ? 'in-stock' : '')}>{item.stock > 0 ? 'У наявності' : 'Тимчасово відсутній'}</span></div>
  </SiteLink></article>
}

export function ProductSection({title, description, items, go, to = '/catalog'}) {
  if (!items?.length) return null
  return <section className="featured shell"><div className="section-row"><div><h2 className="section-heading">{title}</h2>{description && <p className="section-description">{description}</p>}</div><SiteLink className="section-link" to={to} onNavigate={go}>ПЕРЕГЛЯНУТИ ВСІ →</SiteLink></div><div className="products-grid">{items.map(item => <ProductCard key={item.key} item={item} go={go}/>)}</div></section>
}
