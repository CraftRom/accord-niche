import { useEffect, useRef, useState } from 'react'
import { ProfileCard } from './ProfileCard'
import { Field } from '../ui/Field'

const POLL_MS = 3000
const WAIT_MS = 10 * 60 * 1000

// Free phone confirmation: the Telegram bot receives the user's own contact
// (Telegram vouches for the number), or, if the shop runs an SMS gateway,
// a one-time code by SMS. A number typed into a form proves nothing.
export function PhoneVerification({shop, refreshOrders}) {
  const [phone,setPhone]=useState(shop.account.phone || '+380')
  const [code,setCode]=useState('')
  const [sending,setSending]=useState(false)
  const [sent,setSent]=useState(false)
  const [message,setMessage]=useState('')
  const [telegramUrl,setTelegramUrl]=useState('')
  const waitingSince=useRef(0)
  const verified=shop.account.phone_verified
  const refresh=shop.refresh

  // While the bot confirms the number, refresh the profile until it is done.
  useEffect(()=>{
    if(!telegramUrl || verified)return undefined
    const timer=setInterval(()=>{
      if(document.hidden)return
      if(Date.now()-waitingSince.current>WAIT_MS){setTelegramUrl('');setMessage('Посилання застаріло. Натисніть «Підтвердити через Telegram» ще раз.');return}
      refresh().catch(()=>{})
    },POLL_MS)
    return ()=>clearInterval(timer)
  },[telegramUrl,verified,refresh])
  useEffect(()=>{
    if(verified && telegramUrl){setTelegramUrl('');setMessage('Номер підтверджено через Telegram.');refreshOrders?.()}
  },[verified,telegramUrl,refreshOrders])

  const viaTelegram = async () => {
    setSending(true);setMessage('')
    try {
      const {url}=await shop.request('/profile/phone/telegram','POST')
      waitingSince.current=Date.now();setTelegramUrl(url)
      window.open(url,'_blank','noopener')
    } catch(e) {setMessage(e.message)} finally {setSending(false)}
  }
  const action = async (path,payload) => {
    setSending(true);setMessage('')
    try {
      const result=await shop.request(path,'POST',payload)
      if (path.endsWith('/send')) {setSent(true);setMessage('Код надіслано. Введіть його з SMS нижче.')}
      else {setSent(false);setCode('');setMessage(result.note || 'Номер підтверджено');await shop.refresh();refreshOrders?.()}
    } catch(e) {setMessage(e.message)} finally {setSending(false)}
  }
  const available=shop.telegramPhone || shop.smsEnabled
  const status=verified?['ok','Підтверджено']:available?['warn','Потрібне підтвердження']:['off','Недоступно']
  return <ProfileCard title="Контакти та підтвердження" status={status}>
    <p className="shop-hint">{verified ? `Номер ${shop.account.phone} підтверджено.` :
      'Підтвердіть свій номер. Лише підтверджений номер може відкрити історію покупок із Mini App — номер, просто вписаний у форму, її не відкриває.'}</p>
    {!verified && shop.telegramPhone && <div className="phone-telegram">
      <button className="btn primary" disabled={sending} onClick={viaTelegram}>ПІДТВЕРДИТИ ЧЕРЕЗ TELEGRAM</button>
      <p className="shop-hint">Безкоштовно й без коду: бот попросить натиснути «📱 Надіслати номер», і Telegram передасть номер вашого акаунта.</p>
      {telegramUrl && <p className="shop-hint" role="status">Чекаємо підтвердження в боті… Якщо Telegram не відкрився, <a href={telegramUrl} target="_blank" rel="noopener noreferrer">відкрийте бота</a>.</p>}
    </div>}
    {!verified && shop.smsEnabled && <>
      {shop.telegramPhone && <p className="shop-hint phone-or">Або кодом із SMS:</p>}
      <div className="phone-inputs"><Field name="phone" label="Ваш номер" value={phone} onChange={setPhone} placeholder="+380XXXXXXXXX"/>
      <button className="btn outline" disabled={sending} onClick={()=>action('/profile/phone/send',{phone})}>{sending && !sent ? 'НАДСИЛАЄМО…' : sent ? 'НАДІСЛАТИ ЩЕ РАЗ' : 'НАДІСЛАТИ КОД'}</button></div>
      {sent && <div className="phone-inputs"><Field name="code" label="SMS-код" value={code} onChange={setCode} placeholder="123456"/>
        <button className="btn primary" disabled={sending || code.length < 4} onClick={()=>action('/profile/phone/check',{phone,code})}>ПІДТВЕРДИТИ</button></div>}
    </>}
    {!verified && !available && <p className="shop-hint">Підтвердження номера тимчасово недоступне. Історія Telegram не відкривається за непідтвердженим номером.</p>}
    {message && <p className="shop-hint" role="status">{message}</p>}
  </ProfileCard>
}
