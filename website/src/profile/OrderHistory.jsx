import { useState } from 'react'
import { formatAmount } from '../format'
import { StateBlock } from '../ui/states'

// W-23: order status as consecutive stages. Only local statuses map onto the
// stages; a status that comes from the CRM is shown as its own name, never
// forced into a stage it may not mean.
export const STAGES=['Прийнято','В роботі','Відправлено','Отримано']

export const STAGE_OF={new:0,confirmed:0,accepted:1,paid:1,shipped:2,done:3}

// Nova Poshta public tracking page; only for the 14-digit waybill format.
export const trackingUrl=number=>/^\d{14}$/.test(number||'')?'https://novaposhta.ua/tracking/?cargo_number='+number:''

export function OrderStages({order}) {
  if(order.status==='cancelled')return <p className="order-status"><span className="status-chip off">Скасовано</span></p>
  const stage=order.status_source==='local'?STAGE_OF[order.status]:undefined
  return <div className="order-status-block"><p className="order-status">{order.status_label || order.crm_status_name || order.status}</p>
    {stage!==undefined && <ol className="order-steps" aria-label="Етапи замовлення">{STAGES.map((name,i)=><li key={name} className={i<stage?'done':i===stage?'current':''} aria-current={i===stage?'step':undefined}>{name}</li>)}</ol>}</div>
}

export function Tracking({number}) {
  const [copied,setCopied]=useState(false)
  const url=trackingUrl(number)
  const copy=async()=>{try{await navigator.clipboard.writeText(number);setCopied(true);setTimeout(()=>setCopied(false),2000)}catch{setCopied(false)}}
  return <div className="order-tracking"><span>ТТН: <strong>{number}</strong></span>
    {navigator.clipboard && <button className="text-muted-button" onClick={copy} aria-label={'Скопіювати ТТН '+number}>{copied?'Скопійовано':'Скопіювати'}</button>}
    {url && <a className="text-muted-button" href={url} target="_blank" rel="noopener noreferrer">Відстежити на сайті Нової пошти</a>}
    <span className="sr-only" role="status">{copied?'ТТН скопійовано':''}</span></div>
}

export function OrderList({orders,loading,cancelOrder,cancelling}) {
  if(loading) return <StateBlock kind="loading" headingLevel={3}>Завантаження історії замовлень…</StateBlock>
  if(!orders.length) return <StateBlock className="shop-empty" headingLevel={3} title="Історія покупок поки порожня.">Тут з’являться замовлення з сайту та, після зв’язування, з Telegram Mini App.</StateBlock>
  return <div className="order-list">{orders.map(o=><article className="order-record" key={o.id}>
    <div className="order-record-head"><div><strong>Замовлення №{o.id}</strong><span>{o.created_at ? new Date(o.created_at).toLocaleDateString('uk-UA') : ''}</span></div><strong>{formatAmount(o.total)} грн</strong></div>
    <OrderStages order={o}/>
    {o.tracking_number && <Tracking number={o.tracking_number}/>}
    <details className="order-details"><summary>Склад замовлення ({(o.items||[]).length})</summary>
      <ul>{(o.items||[]).map((item,i)=><li key={i}>{item.name} × {item.qty}<span>{formatAmount(Number(item.price)*Number(item.qty))} грн</span></li>)}</ul>
      {o.operator_name && <p>Менеджер: {o.operator_name}</p>}</details>
    {o.can_cancel && <div className="order-cancel"><button className="text-muted-button" disabled={Boolean(cancelling)} onClick={()=>cancelOrder(o.id)}>{cancelling===o.id?'Скасовуємо…':'Скасувати замовлення'}</button></div>}
  </article>)}</div>
}
