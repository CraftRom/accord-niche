import { useEffect, useRef, useState } from 'react'
import { formatAmount } from '../format'
import { GoogleLogin } from './GoogleLogin'
import { OrderList } from './OrderHistory'
import { PhoneVerification } from './PhoneVerification'
import { ProfileCard } from './ProfileCard'
import { TelegramHistoryLink } from './TelegramLink'
import { Field } from '../ui/Field'
import { InlineAlert, StateBlock } from '../ui/states'

export function ProfilePage({shop,go}) {
  const [orders,setOrders] = useState([])
  const [hasMore,setHasMore] = useState(false)
  const [moreLoading,setMoreLoading] = useState(false)
  const [profile,setProfile] = useState(null)
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState('')
  const [newName,setNewName]=useState('')
  const [cancelling,setCancelling]=useState(null)
  const generation=useRef(0)
  const pagination=useRef(null)
  const [historyLoaded,setHistoryLoaded]=useState(false)
  useEffect(()=>()=>{generation.current++;pagination.current=null},[])
  const [saving,setSaving]=useState(false)
  const refreshOrders=async()=>{
    const version=++generation.current
    pagination.current=null;setMoreLoading(false)
    setLoading(true);setError('')
    await Promise.all([shop.request('/orders?limit=30&offset=0'),shop.request('/profile')])
      .then(([result,data])=>{if(version===generation.current){setOrders(result.items||[]);setHasMore(Boolean(result.has_more));setProfile(data);setHistoryLoaded(true)}})
      .catch(e=>{if(version===generation.current)setError(e.message)}).finally(()=>{if(version===generation.current)setLoading(false)})
  }
  const loadMore=async()=>{
    if(loading || pagination.current || !hasMore)return
    const token={version:generation.current}
    pagination.current=token;setMoreLoading(true);setError('')
    const current=()=>pagination.current===token && generation.current===token.version
    try{const result=await shop.request(`/orders?limit=30&offset=${orders.length}`)
      if(current()){
        setOrders(prev=>[...new Map([...prev,...(result.items||[])].map(order=>[order.id,order])).values()]);setHasMore(Boolean(result.has_more))
      }
    }catch(e){if(current())setError(e.message)}
    finally{if(current()){pagination.current=null;setMoreLoading(false)}}
  }
  useEffect(()=>{if(shop.account.has_session)refreshOrders();else setLoading(false)},[shop.account.has_session,shop.account.signed_in,shop.account.telegram_linked])
  const save=async()=>{setSaving(true);setError('');try{await shop.request('/profile','PATCH',{display_name:newName});await shop.refresh();setNewName('')}catch(e){setError(e.message)}finally{setSaving(false)}}
  const logout=async()=>{setError('');try{await shop.request('/auth/logout','POST');await shop.refresh();setOrders([]);setProfile(null)}catch(e){setError(e.message)}}
  const cancelOrder=async id=>{
    if(cancelling)return
    if (!window.confirm(`Скасувати замовлення №${id}? Після скасування потрібно буде оформити нове.`)) return
    setError('')
    setCancelling(id)
    try{await shop.request(`/orders/${id}/cancel`,'POST');await refreshOrders()}
    catch(e){setError(e.message)}finally{setCancelling(null)}
  }
  return <main className="shell commerce-page">
    <p className="eyebrow">ОСОБИСТИЙ КАБІНЕТ</p><h1>Мій профіль</h1>
    <div className="profile-cards">
    {!shop.account.signed_in ? <ProfileCard title="Мій обліковий запис" status={['off','Не підключено']}>
      <p>Увійдіть через Google, щоб бачити всі замовлення сайту з будь-якого пристрою. Вхід не потрібен для покупки — можна замовити як гість.</p>
      <GoogleLogin shop={shop} />
      <p className="shop-hint">Після входу тут з’являться підтвердження телефону й зв’язування покупок із Telegram Mini App.</p>
    </ProfileCard> : <>
    <ProfileCard title="Мій обліковий запис" status={['ok','Google']}>
      <p><strong>{shop.account.name || 'Покупець'}</strong><br/>{shop.account.email}</p>
      <div className="profile-edit"><Field name="displayName" label="Змінити імʼя" required={false} maxLength={100} value={newName} onChange={setNewName} placeholder="Ваше імʼя" />
        <button className="btn outline" disabled={newName.trim().length<2 || saving} onClick={save}>{saving?'ЗБЕРІГАЄМО…':'ЗБЕРЕГТИ'}</button></div>
      {profile && <div className="profile-facts">
        <div><span>Усього замовлень</span><strong>{profile.orders_count}</strong></div>
        <div><span>Бонуси сайту</span><strong>{formatAmount(profile.bonus_balance)} грн</strong></div>
        {profile.latest_delivery?.city && <div><span>Остання доставка</span><strong>{profile.latest_delivery.city}, {profile.latest_delivery.address}</strong></div>}
      </div>}
      <button className="text-muted-button" onClick={logout}>Вийти з профілю</button>
    </ProfileCard>
      <PhoneVerification shop={shop} refreshOrders={refreshOrders}/>
      <TelegramHistoryLink shop={shop} refreshOrders={refreshOrders}/>
    </>}
    </div>
    <section className="orders-section"><div className="section-row"><h2>Історія покупок</h2><button className="text-muted-button" onClick={refreshOrders} disabled={!shop.account.has_session || loading}>Оновити</button></div>
      <InlineAlert>{error}</InlineAlert>
      {shop.account.has_session ? <>{(loading || historyLoaded) && <OrderList orders={orders} loading={loading} cancelOrder={cancelOrder} cancelling={cancelling} />}{hasMore && !loading && <button className="btn outline" disabled={moreLoading} onClick={loadMore}>{moreLoading?'ЗАВАНТАЖУЄМО…':'ПОКАЗАТИ БІЛЬШЕ ЗАМОВЛЕНЬ'}</button>}</> : <StateBlock className="shop-empty" headingLevel={3} title="Після першого замовлення історія з’явиться тут.">Щоб вона зберігалась між пристроями, увійдіть через Google.</StateBlock>}
    </section><button className="btn outline" onClick={()=>go('/catalog')}>ПРОДОВЖИТИ ПОКУПКИ</button>
  </main>
}
