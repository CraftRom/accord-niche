import { useState } from 'react'
import { ProfileCard } from './ProfileCard'
import { Field } from '../ui/Field'

export function TelegramHistoryLink({shop, refreshOrders}) {
  const [code,setCode] = useState('')
  const [message,setMessage] = useState('')
  const [busy,setBusy] = useState(false)
  if(shop.account.telegram_linked) return <ProfileCard title="Покупки з Telegram" status={['ok','Підключено']}>
    <p className="shop-hint">Замовлення з Telegram Mini App показуються в історії нижче разом із замовленнями сайту.</p></ProfileCard>
  const link=async()=>{
    setBusy(true);setMessage('')
    try {
      const data=await shop.request('/profile/link-code','POST',{code:code.trim()})
      setMessage(data.note);setCode('');await shop.refresh();refreshOrders?.()
    }catch(e){setMessage(e.message)}finally{setBusy(false)}
  }
  return <ProfileCard title="Покупки з Telegram" status={['off','Не підключено']}>
    <p className="shop-hint">Вхід через Google і зв’язування — різні речі: вхід зберігає замовлення сайту, а зв’язування додає до них історію з Mini App. Якщо раніше купували через Mini App, відкрийте в ньому Профіль → «Створити код звʼязування». Вставте код сюди. Він підтверджує саме ваш Telegram-акаунт і відкриває попередню історію покупок навіть без SMS.</p>
    <div className="phone-inputs"><Field name="telegramCode" label="Одноразовий код із Mini App" value={code} onChange={setCode} placeholder="Код із Telegram"/>
      <button className="btn outline" onClick={link} disabled={busy || code.trim().length < 18}>{busy ? 'ЗВʼЯЗУЄМО…' : 'ЗВʼЯЗАТИ'}</button></div>
    {message && <p className="shop-hint" role="status">{message}</p>}
  </ProfileCard>
}
