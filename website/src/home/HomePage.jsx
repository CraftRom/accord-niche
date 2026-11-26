import { ProductSection } from '../catalog/ProductCard'
import { money } from '../format'
import { SiteLink } from '../router'
import { ImageTile } from '../ui/ImageTile'
import { RequestStatus } from '../ui/RequestStatus'
import { useStoreRequest } from '../useStoreRequest'
import { aromaPath } from '../catalog/aromaPath'

// W-16: one dominant action; the formats line appears only when the live
// assortment confirms it, never as a hard-coded promise.
export function volumesOf(items = []) {
  return [...new Set(items.flatMap(item => item.volumes || []).map(Number).filter(v => v > 0))].sort((a, b) => a - b)
}

export function Hero({go, item, volumes = []}) {
  const target = item ? aromaPath(item) : ''
  return <section className="hero shell" aria-labelledby="hero-title"><div className="hero-content"><p className="eyebrow">НІШЕВА ПАРФУМЕРІЯ У ВАШОМУ ФОРМАТІ</p><h1 id="hero-title">Знайдіть аромат,<br/>який стане<br/>вашим</h1><p className="hero-description">Обирайте аромат і зручний об’єм. Знайомтеся з парфумерією у власному ритмі — перед рішенням про повний флакон.</p>
    {volumes.length > 0 && <p className="hero-formats">Об’єми {volumes.join(' / ')} мл · ціна за мілілітр біля кожного аромату</p>}
    <div className="hero-cta"><SiteLink className="btn primary" to="/catalog" onNavigate={go}>ОБРАТИ АРОМАТ</SiteLink><SiteLink className="hero-secondary" to="/catalog?kind=new" onNavigate={go}>Новинки <span aria-hidden="true">→</span></SiteLink></div></div>
    {item?.image ? <SiteLink className="hero-product" to={target} onNavigate={go}><ImageTile item={item} className="hero-tile" priority sizes="(max-width: 750px) 100vw, 45vw"/><span><b>{[item.brand, item.name].filter(Boolean).join(' · ')}</b>{item.min_price != null && <em>від {money(item.min_price)}</em>}</span></SiteLink> : <div className="hero-lettering" aria-hidden="true"><span>A</span><p>ACCORD NICHE</p><i>Ваш аромат. Ваш формат.</i></div>}</section>
}

// W-17: answers to «what is in the vial, what does it cost, when is it sent,
// what if something is wrong» — only facts the shop actually provides.
export function BuyerFacts({volumes = [], go}) {
  const facts = [
    ['Формат', volumes.length ? `Розпив в об’ємах ${volumes.join(' / ')} мл: спробуйте аромат, перш ніж купувати флакон.` : 'Розпив у невеликих об’ємах: спробуйте аромат, перш ніж купувати флакон.'],
    ['Чесна ціна', 'Біля кожного аромату — ціна за мілілітр, тож об’єми легко порівняти. Підсумок із доставкою видно до підтвердження.'],
    ['Доставка', 'Новою поштою. Статус замовлення й номер ТТН — в історії покупок особистого кабінету.'],
    ['Якщо щось не так', 'До відправлення замовлення можна скасувати в кабінеті. З питаннями щодо отриманого товару — контакти внизу сторінки.'],
  ]
  return <section className="buyer-facts shell" aria-labelledby="facts-title"><h2 id="facts-title" className="section-heading">Перед замовленням</h2>
    <div className="facts-grid">{facts.map(([title, text]) => <article key={title}><h3>{title}</h3><p>{text}</p></article>)}</div>
    <SiteLink className="section-link" to="/how" onNavigate={go}>ЯК ЦЕ ПРАЦЮЄ →</SiteLink></section>
}

export function HowItWorks() {
  return <section className="how-section"><div className="shell"><h2 className="section-heading light">Як це працює</h2><div className="steps"><article><span className="step-number">01</span><h3>Обираєте аромат</h3><p>Порівнюйте бренди, доступні об’єми та ціни за мілілітр.</p></article><article><span className="step-number">02</span><h3>Оформлюєте замовлення</h3><p>Додайте потрібний об’єм у кошик і оберіть спосіб доставки.</p></article><article><span className="step-number">03</span><h3>Стежите за доставкою</h3><p>Історія замовлень і актуальний статус доступні в особистому кабінеті.</p></article></div></div></section>
}

export function Home({go}) {
  const request = useStoreRequest('/api/public/storefront')
  const data = request.data
  const volumes = volumesOf(data?.selection)
  return <main><Hero go={go} item={data?.selection?.[0]} volumes={volumes}/><div className="shell"><RequestStatus request={request} empty={data?.total === 0}/></div>
    {data && <>{data.hits.length > 0 ? <ProductSection title="Хіти розпиву" description={'Найпопулярніші за підтвердженими продажами за ' + data.window_days + ' днів.'} items={data.hits} go={go} to="/catalog?kind=hits"/> : <ProductSection title="Оберіть свій аромат" description="Товари з актуального каталогу магазину." items={data.selection} go={go}/>}
      {data.total > 0 && <BuyerFacts volumes={volumes} go={go}/>}<ProductSection title="Новинки" items={data.new_arrivals} go={go} to="/catalog?kind=new"/><ProductSection title="Рекомендуємо" description="Добірка магазину для знайомства з ароматами." items={data.recommended} go={go} to="/catalog?kind=recommended"/></>}<HowItWorks/></main>
}
