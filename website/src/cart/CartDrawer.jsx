import { useRef } from 'react'
import { telegramCheckoutUrl } from '../catalog'
import { money } from '../format'
import { Icon } from '../ui/Icon'
import { ImageTile } from '../ui/ImageTile'
import { useDialog } from '../useDialog'

export function Basket({open, close, cart, products, change, go, site, request, lineNotes = {}}) {
  const dialog=useRef(null)
  useDialog(dialog,open,close)
  if (!open) return null
  const lines = Object.entries(cart).map(([id,qty]) => ({product:products.find(product => product.id === Number(id)), qty:Number(qty)})).filter(line => line.product)
  const unresolved=Object.keys(cart).filter(id=>!products.some(product=>product.id===Number(id)))
  const total = lines.reduce((sum,line) => sum + Number(line.product.price) * line.qty, 0)
  const link = telegramCheckoutUrl(site.miniapp_url || '', cart, products)
  const blocked = Boolean(request.loading || request.error || Object.keys(cart).length !== lines.length)
  return <div className="drawer-backdrop" onMouseDown={event => {if (event.target === event.currentTarget) close()}}><aside ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Кошик" className="basket"><div className="basket-head"><h2>Кошик</h2><button className="icon-btn" aria-label="Закрити кошик" onClick={close}><Icon name="close"/></button></div>
    <div className="basket-lines">{Object.keys(cart).length > 0 && request.error && <div role="alert" className="notice">Не вдалося перевірити кошик. <button onClick={request.retry}>Спробувати ще раз</button></div>}{request.loading && <p role="status" className="shop-hint">Перевіряємо ціни й наявність…</p>}
      {unresolved.map(id=><div className="basket-line" key={id}><p>Товар потребує перевірки наявності.</p><button className="remove-btn" onClick={()=>change(Number(id),0)}>Прибрати з кошика</button></div>)}{lines.map(({product,qty}) => <div className="basket-line" key={product.id}><div className="basket-thumb"><ImageTile item={product}/></div><div className="basket-info"><h3>{product.brand && product.brand + ' · '}{product.name}</h3><p>{[product.volume_ml ? product.volume_ml + ' мл' : '', money(product.price) + ' за шт.'].filter(Boolean).join(' · ')}</p><strong>{qty > 1 ? qty + ' × ' + money(product.price) + ' = ' : ''}{money(Number(product.price) * qty)}</strong>{lineNotes[product.id] && <p className="basket-line-note" role="status">{lineNotes[product.id]}</p>}<div className="qty-control" role="group" aria-label={'Кількість: ' + product.name}><button aria-label={'Зменшити кількість: ' + product.name} onClick={() => change(product.id, qty - 1)}>−</button><span aria-live="polite">{qty}</span><button aria-label={'Збільшити кількість: ' + product.name} disabled={qty >= product.stock || qty >= 99} onClick={() => change(product.id, qty + 1)}>+</button><button className="remove-btn" aria-label={'Видалити з кошика: ' + product.name} onClick={() => change(product.id, 0)}>Видалити</button></div>{qty >= product.stock && product.stock < 99 && <p className="basket-line-hint">У наявності {product.stock} шт. — це максимум.</p>}</div></div>)}
      {!Object.keys(cart).length && <div className="empty-basket"><p>У кошику поки порожньо</p><button className="btn outline" onClick={() => {close(); go('/catalog')}}>Переглянути аромати</button></div>}</div>
    {lines.length > 0 && <div className="basket-bottom"><div className="basket-total"><span>Сума за товари</span><strong>{money(total)}</strong></div><button className="btn primary checkout-link" disabled={blocked} onClick={() => {close(); go('/checkout')}}>ОФОРМИТИ ЗАМОВЛЕННЯ →</button>{!blocked && link && <a className="basket-telegram-link" href={link} target="_blank" rel="noopener noreferrer">Продовжити в Telegram Mini App</a>}<p>Доставка не входить у суму: її оплачують перевізнику за його тарифами. Знижки, бонуси й остаточну суму покаже оформлення. Кошик зберігається на цьому пристрої.</p></div>}</aside></div>
}
