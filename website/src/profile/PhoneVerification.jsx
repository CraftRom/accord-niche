import { useState } from 'react'
import { ProfileCard } from './ProfileCard'
import { Field } from '../ui/Field'

export function PhoneVerification({shop, refreshOrders}) {
  const [phone,setPhone]=useState(shop.account.phone || '+380')
  const [code,setCode]=useState('')
  const [sending,setSending]=useState(false)
  const [sent,setSent]=useState(false)
  const [message,setMessage]=useState('')
  const action = async (path,payload) => {
    setSending(true);setMessage('')
    try {
      const result=await shop.request(path,'POST',payload)
      if (path.endsWith('/send')) {setSent(true);setMessage('Код надіслано. Введіть його з SMS нижче.')}
      else {setSent(false);setCode('');setMessage(result.note || 'Номер підтверджено');await shop.refresh();refreshOrders?.()}
    } catch(e) {setMessage(e.message)} finally {setSending(false)}
  }
  const status=shop.account.phone_verified?['ok','Підтверджено']:shop.smsEnabled?['warn','Потрібне підтвердження']:['off','Недоступно']
  return <ProfileCard title="Контакти та підтвердження" status={status}>
    <p className="shop-hint">{shop.account.phone_verified ? `Номер ${shop.account.phone} підтверджено кодом із SMS.` :
      'Підтвердіть номер кодом із SMS. Лише підтверджений номер може відкрити історію покупок із Mini App — номер, просто вписаний у форму, її не відкриває.'}</p>
    {shop.smsEnabled ? <>
      <div className="phone-inputs"><Field name="phone" label="Ваш номер" value={phone} onChange={setPhone} placeholder="+380XXXXXXXXX"/>
      <button className="btn outline" disabled={sending} onClick={()=>action('/profile/phone/send',{phone})}>{sending && !sent ? 'НАДСИЛАЄМО…' : sent ? 'НАДІСЛАТИ ЩЕ РАЗ' : 'НАДІСЛАТИ КОД'}</button></div>
      {sent && <div className="phone-inputs"><Field name="code" label="SMS-код" value={code} onChange={setCode} placeholder="123456"/>
        <button className="btn primary" disabled={sending || code.length < 4} onClick={()=>action('/profile/phone/check',{phone,code})}>ПІДТВЕРДИТИ</button></div>}
    </> : <p className="shop-hint">SMS-підтвердження не налаштовано. Додавати номер без перевірки небезпечно, тому історія Telegram не відкривається за непідтвердженим номером.</p>}
    {message && <p className="shop-hint" role="status">{message}</p>}
  </ProfileCard>
}
