import { useCallback, useEffect, useRef, useState } from 'react'
import {phoneNumber,checkoutErrors,readCheckoutAttempt,rememberCheckoutAttempt,clearCheckoutAttempt,checkoutCampaign} from './checkout'

const money = (amount) => new Intl.NumberFormat('uk-UA', { maximumFractionDigits:2 }).format(Number(amount || 0))

async function parseResponse(response) {
  const payload = await response.json().catch(()=>({}))
  if (!response.ok) {
    const raw = payload?.detail
    const error=new Error(typeof raw === 'string' ? raw :
      Array.isArray(raw) ? raw.map(x=>x.msg).join('; ') : `Не вдалося виконати запит (${response.status})`)
    error.status=response.status;error.issues=Array.isArray(raw)?raw:[];error.code=payload.code
    throw error
  }
  return payload
}

async function customerFetch(url,options={}) {
  const controller=new AbortController()
  const timer=setTimeout(()=>controller.abort(),20000)
  try{return await parseResponse(await fetch(url,{...options,signal:controller.signal}))}
  catch(error){
    if(error.name==='AbortError')throw new Error('Сервер не відповів вчасно. Перевірте з’єднання та повторіть дію.')
    throw error
  }finally{clearTimeout(timer)}
}

export function useCommerce() {
  const [account, setAccount] = useState({ signed_in:false, has_session:false })
  const [googleClient, setGoogleClient] = useState('')
  const [smsEnabled, setSmsEnabled] = useState(false)
  const [ready, setReady] = useState(false)
  const csrfRef = useRef('')
  const sessionRequest=useRef(null)
  const loadSession = useCallback(() => {
    if(sessionRequest.current)return sessionRequest.current
    sessionRequest.current=customerFetch('/api/web/session',{credentials:'include',cache:'no-store'})
      .then(payload=>{
        csrfRef.current=payload.csrf;setAccount(payload.account)
        setGoogleClient(payload.google_client_id || '');setSmsEnabled(Boolean(payload.phone_verification_enabled));setReady(true)
        return payload
      }).finally(()=>{sessionRequest.current=null})
    return sessionRequest.current
  }, [])
  useEffect(()=>{loadSession().catch(()=>setReady(true))},[loadSession])
  const request = useCallback(async (endpoint, method='GET', data) => {
    if (!csrfRef.current) await loadSession()
    try {
      const result=await customerFetch(`/api/web${endpoint}`, {
      method, credentials:'include', cache:'no-store',
      headers: {...(method !== 'GET' ? {'Content-Type':'application/json','X-CSRF-Token':csrfRef.current}: {})},
      ...(data !== undefined ? {body:JSON.stringify(data)} : {}),
      })
      if(endpoint==='/auth/logout')clearCheckoutAttempt()
      return result
    }catch(error){
      if(error.status===401){clearCheckoutAttempt();csrfRef.current='';setAccount({signed_in:false,has_session:false})}
      throw error
    }
  },[loadSession])
  return {account, googleClient, smsEnabled, ready, refresh:loadSession, request}
}

function Field({name, label, value, onChange, required=true, type='text', placeholder='', autoComplete, maxLength,error}) {
  const id='accord-'+name
  return <label className="shop-field" htmlFor={id}><span>{label}{required ? ' *' : ''}</span><input id={id} name={name} type={type} value={value} required={required}
    aria-invalid={error?true:undefined} aria-describedby={error?id+'-error':undefined}
    maxLength={maxLength} placeholder={placeholder} autoComplete={autoComplete} onChange={e=>onChange(e.target.value)} />
    {error && <small className="field-error" id={id+'-error'}>{error}</small>}</label>
}

function GoogleLogin({ shop }) {
  const node = useRef(null)
  const [error,setError] = useState('')
  const secure = location.protocol === 'https:' || ['localhost','127.0.0.1'].includes(location.hostname)
  useEffect(()=>{
    if (!shop.googleClient || !secure || shop.account.signed_in) return
    let active=true
    const initialize=()=>{
      if (!active || !node.current || !window.google?.accounts?.id) return
      window.google.accounts.id.initialize({client_id:shop.googleClient,callback: async ({credential})=>{
        try {setError('');await shop.request('/auth/google','POST',{credential});await shop.refresh()}
        catch(e) {setError(e.message)}
      }})
      window.google.accounts.id.renderButton(node.current,{theme:'outline',size:'large',width:300,shape:'rectangular',text:'continue_with'})
    }
    if(window.google?.accounts?.id) initialize()
    else {
      let script=document.querySelector('script[data-accord-google]')
      if (!script) {
        script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';
        script.async=true;script.defer=true;script.dataset.accordGoogle='1';document.head.appendChild(script)
      }
      script.addEventListener('load',initialize)
      return ()=>{active=false;script.removeEventListener('load',initialize)}
    }
    return ()=>{active=false}
  },[shop.googleClient,shop.account.signed_in])
  if (!shop.googleClient) return <p className="shop-hint">Google-вхід поки не підключено. Замовлення без реєстрації доступне.</p>
  if (!secure) return <p className="shop-hint">Для Google-входу потрібен HTTPS. На тестовому HTTP/IP працює оформлення без реєстрації.</p>
  return <div><div ref={node} className="google-slot"/>{error && <p className="shop-error" role="alert">{error}</p>}</div>
}

function TelegramHistoryLink({shop, refreshOrders}) {
  const [code,setCode] = useState('')
  const [message,setMessage] = useState('')
  const [busy,setBusy] = useState(false)
  if(shop.account.telegram_linked) return null
  const link=async()=>{
    setBusy(true);setMessage('')
    try {
      const data=await shop.request('/profile/link-code','POST',{code:code.trim()})
      setMessage(data.note);setCode('');await shop.refresh();refreshOrders?.()
    }catch(e){setMessage(e.message)}finally{setBusy(false)}
  }
  return <div className="verification-panel"><h3>Звʼязати з Telegram Mini App</h3>
    <p className="shop-hint">Якщо раніше купували через Mini App, відкрийте в ньому Профіль → «Створити код звʼязування». Вставте код сюди. Він підтверджує саме ваш Telegram-акаунт і відкриває попередню історію покупок навіть без SMS.</p>
    <div className="phone-inputs"><Field name="telegramCode" label="Одноразовий код із Mini App" value={code} onChange={setCode} placeholder="Код із Telegram"/>
      <button className="btn outline" onClick={link} disabled={busy || code.trim().length < 18}>ЗВʼЯЗАТИ</button></div>
    {message && <p className="shop-hint" role="status">{message}</p>}
  </div>
}

function PhoneVerification({shop, refreshOrders}) {
  const [phone,setPhone]=useState(shop.account.phone || '+380')
  const [code,setCode]=useState('')
  const [sending,setSending]=useState(false)
  const [sent,setSent]=useState(false)
  const [message,setMessage]=useState('')
  const action = async (path,payload) => {
    setSending(true);setMessage('')
    try {
      const result=await shop.request(path,'POST',payload)
      if (path.endsWith('/send')) {setSent(true);setMessage('Код надіслано. Введи його з SMS нижче.')}
      else {setSent(false);setCode('');setMessage(result.note || 'Номер підтверджено');await shop.refresh();refreshOrders?.()}
    } catch(e) {setMessage(e.message)} finally {setSending(false)}
  }
  return <div className="verification-panel">
    <h3>Номер телефону</h3>
    <p className="shop-hint">{shop.account.phone_verified ? `Підтверджено: ${shop.account.phone}` :
      'Підтверди свій номер, щоб безпечно звʼязати історію покупок із Mini App.'}</p>
    {shop.account.telegram_linked && <p className="shop-success">Історію Telegram-покупок підключено.</p>}
    {shop.smsEnabled ? <>
      <div className="phone-inputs"><Field name="phone" label="Твій номер" value={phone} onChange={setPhone} placeholder="+380XXXXXXXXX"/>
      <button className="btn outline" disabled={sending} onClick={()=>action('/profile/phone/send',{phone})}>НАДІСЛАТИ КОД</button></div>
      {sent && <div className="phone-inputs"><Field name="code" label="SMS-код" value={code} onChange={setCode} placeholder="123456"/>
        <button className="btn primary" disabled={sending || code.length < 4} onClick={()=>action('/profile/phone/check',{phone,code})}>ПІДТВЕРДИТИ</button></div>}
    </> : <p className="shop-hint">SMS-підтвердження не налаштовано. Додавати номер без перевірки небезпечно, тому історія Telegram не відкривається за непідтвердженим номером.</p>}
    {message && <p className="shop-hint" role="status">{message}</p>}
  </div>
}

function OrderList({orders,loading,cancelOrder,cancelling}) {
  if(loading) return <p className="shop-hint">Завантаження історії замовлень…</p>
  if(!orders.length) return <div className="shop-empty">Історія покупок поки порожня.</div>
  return <div className="order-list">{orders.map(o=><article className="order-record" key={o.id}>
    <div className="order-record-head"><div><strong>Замовлення №{o.id}</strong><span>{o.created_at ? new Date(o.created_at).toLocaleDateString('uk-UA') : ''}</span></div><strong>{money(o.total)} грн</strong></div>
    <p className="order-status">{o.status_label || o.crm_status_name || o.status}</p>
    <ul>{(o.items||[]).map((item,i)=><li key={i}>{item.name} × {item.qty}<span>{money(Number(item.price)*Number(item.qty))} грн</span></li>)}</ul>
    {o.tracking_number && <p>ТТН: <strong>{o.tracking_number}</strong></p>}
    {o.operator_name && <p>Менеджер: {o.operator_name}</p>}
    {o.can_cancel && <button className="text-muted-button" disabled={Boolean(cancelling)} onClick={()=>cancelOrder(o.id)}>Скасувати замовлення</button>}
  </article>)}</div>
}

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
    {!shop.account.signed_in ? <section className="commerce-panel">
      <h2>Увійди через Google</h2><p>Усі замовлення в одному місці. Вхід не потрібен для покупки — можна замовити як гість.</p>
      <GoogleLogin shop={shop} />
    </section> : <section className="commerce-panel">
      <h2>{shop.account.name || 'Покупець'}</h2><p>{shop.account.email}</p>
      <div className="profile-edit"><Field name="displayName" label="Змінити імʼя" required={false} maxLength={100} value={newName} onChange={setNewName} placeholder="Твоє імʼя" />
        <button className="btn outline" disabled={newName.trim().length<2 || saving} onClick={save}>ЗБЕРЕГТИ</button></div>
      {profile && <div className="profile-facts">
        <div><span>Усього замовлень</span><strong>{profile.orders_count}</strong></div>
        <div><span>Бонуси сайту</span><strong>{money(profile.bonus_balance)} грн</strong></div>
        {profile.latest_delivery?.city && <div><span>Остання доставка</span><strong>{profile.latest_delivery.city}, {profile.latest_delivery.address}</strong></div>}
      </div>}
      <PhoneVerification shop={shop} refreshOrders={refreshOrders}/>
      <TelegramHistoryLink shop={shop} refreshOrders={refreshOrders}/>
      <button className="text-muted-button" onClick={logout}>Вийти з профілю</button>
    </section>}
    <section className="orders-section"><div className="section-row"><h2>Історія покупок</h2><button className="text-muted-button" onClick={refreshOrders} disabled={!shop.account.has_session || loading}>Оновити</button></div>
      {error && <p className="shop-error" role="alert">{error}</p>}
      {shop.account.has_session ? <>{(loading || historyLoaded) && <OrderList orders={orders} loading={loading} cancelOrder={cancelOrder} cancelling={cancelling} />}{hasMore && !loading && <button className="btn outline" disabled={moreLoading} onClick={loadMore}>{moreLoading?'ЗАВАНТАЖУЄМО…':'ПОКАЗАТИ БІЛЬШЕ ЗАМОВЛЕНЬ'}</button>}</> : <div className="shop-empty">Після першого замовлення історія зʼявиться тут. Для збереження між пристроями увійди через Google.</div>}
    </section><button className="btn outline" onClick={()=>go('/catalog')}>ПРОДОВЖИТИ ПОКУПКИ</button>
  </main>
}

const emptyCheckout=()=>({contact_surname:'',contact_name:'',contact_patronymic:'',contact_phone:'',city:'',address:'',delivery_method:'warehouse',payment_method:'cod',promo_code:'',comment:'',terms_accepted:false,use_bonus:false})
function checkoutForm(payload={}) {
  const result=emptyCheckout()
  for(const name of Object.keys(result))if(payload[name]!=null)result[name]=payload[name]
  return result
}

export function CheckoutPage({shop,cart,products,go,complete,cartRequest,change}) {
  const [attempt,setAttempt]=useState(readCheckoutAttempt)
  const [form,setForm]=useState(()=>checkoutForm(attempt?.payload))
  const [quote,setQuote]=useState(null)
  const [quoting,setQuoting]=useState(false)
  const [submitting,setSubmitting]=useState(false)
  const [checking,setChecking]=useState(false)
  const [error,setError]=useState('')
  const [errors,setErrors]=useState({})
  const [np,setNp]=useState({courier_enabled:false,novaposhta_enabled:false})
  const [npLoaded,setNpLoaded]=useState(false)
  const [deliveryNote,setDeliveryNote]=useState('')
  const [cityOptions,setCityOptions]=useState([])
  const [warehouseOptions,setWarehouseOptions]=useState([])
  const [directoryBusy,setDirectoryBusy]=useState('')
  const [cityRef,setCityRef]=useState(attempt?.payload.delivery_city_ref || '')
  const [settlementRef,setSettlementRef]=useState('')
  const [warehouseRef,setWarehouseRef]=useState(attempt?.payload.delivery_warehouse_ref || '')
  const pristine=useRef(!attempt)
  const busy=useRef(false)
  const quoteSequence=useRef(0)
  const alive=useRef(true)
  const alert=useRef(null)
  const lines=Object.entries(cart).map(([id,qty])=>({product:products.find(product=>product.id===Number(id)),qty:Number(qty)})).filter(line=>line.product && line.qty>0)
  const items=lines.map(({product,qty})=>({product_id:product.id,qty}))
  const signature=JSON.stringify([items,lines.map(line=>String(line.product.price)),form.promo_code.trim(),form.use_bonus])
  const latest=useRef(signature);latest.current=signature
  const currentQuote=quote?.signature===signature?quote:null
  const blocked=Boolean(cartRequest?.loading || cartRequest?.error || lines.length!==Object.keys(cart).length)
  const shownLines=attempt?.lines || lines
  const subtotal=shownLines.reduce((sum,line)=>sum+Number(line.product.price)*line.qty,0)
  const locked=Boolean(attempt || submitting)
  useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[])
  useEffect(()=>{
    if(!attempt)return
    const guard=event=>{event.preventDefault();event.returnValue=''}
    window.addEventListener('beforeunload',guard)
    return()=>window.removeEventListener('beforeunload',guard)
  },[attempt])
  function update(field,value) {
    pristine.current=false
    setForm(previous=>({...previous,[field]:value}))
    setErrors(previous=>({...previous,[field]:''}))
  }
  useEffect(()=>{
    let active=true
    shop.request('/delivery/config').then(value=>{if(active)setNp(value)}).catch(()=>{if(active)setDeliveryNote('Довідник доставки тимчасово недоступний. Введіть адресу вручну.')}).finally(()=>{if(active)setNpLoaded(true)})
    return()=>{active=false}
  },[])
  useEffect(()=>{
    if(!shop.account.has_session || !npLoaded || attempt)return
    let active=true
    shop.request('/checkout/defaults').then(data=>{
      if(!active || !pristine.current)return
      const method=data.delivery_method==='courier' && np.courier_enabled?'courier':'warehouse'
      const compatible=!data.delivery_method || data.delivery_method===method
      setForm(previous=>({...previous,contact_surname:data.contact_surname || '',contact_name:data.contact_name || '',contact_patronymic:data.contact_patronymic || '',contact_phone:data.contact_phone || '',city:data.city || '',address:compatible?data.address || '':'',delivery_method:method,payment_method:['cod','card'].includes(data.payment_method)?data.payment_method:'cod'}))
      setCityRef(data.delivery_city_ref || '');setWarehouseRef(compatible&&method==='warehouse'?data.delivery_warehouse_ref || '':'')
    }).catch(()=>{})
    return()=>{active=false}
  },[shop.account.has_session,npLoaded,np.courier_enabled,Boolean(attempt)])
  useEffect(()=>{
    setCityOptions([])
    if(!np.novaposhta_enabled || cityRef || form.city.trim().length<2 || locked)return
    let active=true
    const timer=setTimeout(()=>{
      setDirectoryBusy('city')
      shop.request('/delivery/cities?q='+encodeURIComponent(form.city.trim())).then(result=>{if(active){setCityOptions(result.items || []);setDeliveryNote(result.manual?'Довідник недоступний. Введіть населений пункт і адресу вручну.':'')}})
        .catch(()=>{if(active)setDeliveryNote('Не вдалося завантажити міста. Доступне ручне введення.')}).finally(()=>{if(active)setDirectoryBusy('')})
    },350)
    return()=>{active=false;clearTimeout(timer);setDirectoryBusy('')}
  },[np.novaposhta_enabled,form.city,cityRef,locked])
  useEffect(()=>{
    setWarehouseOptions([])
    if(!np.novaposhta_enabled || form.delivery_method!=='warehouse' || (!cityRef&&!settlementRef) || warehouseRef || locked)return
    let active=true
    const timer=setTimeout(()=>{
      setDirectoryBusy('warehouse')
      shop.request('/delivery/warehouses?city_ref='+encodeURIComponent(cityRef)+'&settlement_ref='+encodeURIComponent(settlementRef)+'&q='+encodeURIComponent(form.address)).then(result=>{if(active){setWarehouseOptions(result.items || []);setDeliveryNote(result.manual?'Довідник недоступний. Вкажіть відділення або поштомат вручну.':'')}})
        .catch(()=>{if(active)setDeliveryNote('Не вдалося завантажити відділення. Доступне ручне введення.')}).finally(()=>{if(active)setDirectoryBusy('')})
    },350)
    return()=>{active=false;clearTimeout(timer);setDirectoryBusy('')}
  },[np.novaposhta_enabled,form.delivery_method,cityRef,settlementRef,form.address,warehouseRef,locked])
  async function preview() {
    if(blocked || !items.length || attempt || busy.current)return null
    const sequence=++quoteSequence.current,captured=signature
    setQuoting(true);setError('')
    try {
      const value=await shop.request('/checkout/quote','POST',{items,promo_code:form.promo_code.trim()||null,use_bonus:form.use_bonus})
      if(alive.current && sequence===quoteSequence.current && latest.current===captured){setQuote({...value,signature:captured});shop.refresh().catch(()=>{})}
      return value
    }catch(error){if(alive.current && sequence===quoteSequence.current && latest.current===captured){setQuote(null);setError(error.message)}return null}
    finally{if(alive.current && sequence===quoteSequence.current)setQuoting(false)}
  }
  useEffect(()=>{
    if(!shop.ready || attempt || blocked || !items.length)return
    const timer=setTimeout(preview,400)
    return()=>clearTimeout(timer)
  },[signature,shop.ready,blocked,Boolean(attempt)])
  function finish(result) {
    if(!Number.isSafeInteger(result.order_id) || result.order_id<=0)throw new Error('Не вдалося перевірити номер замовлення. Повторіть перевірку.')
    clearCheckoutAttempt();setAttempt(null);complete(result);go('/order/success')
  }
  async function recover() {
    if(!attempt || busy.current)return
    busy.current=true;setChecking(true);setError('')
    try {
      const result=await shop.request('/checkout/status?checkout_key='+encodeURIComponent(attempt.payload.checkout_key))
      if(result.found)finish(result)
    }catch(error){if(alive.current){setError(error.message);if(error.status===401){setAttempt(null);setForm(emptyCheckout())}}}
    finally{busy.current=false;if(alive.current)setChecking(false)}
  }
  useEffect(()=>{if(shop.ready && attempt)recover()},[shop.ready])
  async function submit(event) {
    event.preventDefault()
    if(busy.current || quoting || checking)return
    let outgoing=attempt
    if(!outgoing) {
      if(blocked || !lines.length)return
      if(!currentQuote){await preview();return}
      const validation=checkoutErrors(form)
      setErrors(validation)
      if(Object.keys(validation).length){setError('Перевірте позначені поля. Ваші дані збережено у формі.');requestAnimationFrame(()=>document.querySelector('#accord-checkout [aria-invalid="true"]')?.focus());return}
      const payload={...form,attribution:checkoutCampaign(),contact_surname:form.contact_surname.trim(),contact_name:form.contact_name.trim(),contact_patronymic:form.contact_patronymic.trim()||null,contact_phone:phoneNumber(form.contact_phone),city:form.city.trim(),address:form.address.trim(),delivery_city_ref:cityRef||null,delivery_warehouse_ref:form.delivery_method==='warehouse'?warehouseRef||null:null,promo_code:form.promo_code.trim()||null,comment:form.comment.trim()||null,quote_token:currentQuote.quote_token,checkout_key:crypto.randomUUID().replaceAll('-','')}
      outgoing={payload,lines:lines.map(line=>({product:{...line.product,price:currentQuote.items?.find(item=>item.product_id===line.product.id)?.unit_price ?? line.product.price},qty:line.qty})),total:currentQuote.total}
      rememberCheckoutAttempt(outgoing);setAttempt(outgoing)
    }
    busy.current=true;setSubmitting(true);setError('')
    try{finish(await shop.request('/checkout','POST',outgoing.payload))}
    catch(error){
      if(alive.current){
        setError(error.message)
        if(error.status>=400 && error.status<500){
          clearCheckoutAttempt();setAttempt(null);setQuote(null)
          const fields={}
          for(const issue of error.issues || []){const name=issue.loc?.at(-1);if(name in form)fields[name]=issue.msg}
          setErrors(fields)
          if(error.status===401)setForm(emptyCheckout())
          else cartRequest?.retry()
        }
        requestAnimationFrame(()=>alert.current?.focus())
      }
    }finally{busy.current=false;if(alive.current)setSubmitting(false)}
  }
  const quoteLines=new Map((currentQuote?.items || []).map(line=>[line.product_id,line]))
  return <main className="shell commerce-page"><button className="back-link" onClick={()=>go('/catalog')}>← Повернутися в каталог</button><p className="eyebrow">ОФОРМЛЕННЯ ПОКУПКИ</p><h1>Ваше замовлення</h1>
    {attempt && <section className="checkout-recovery" role="status"><h2>Перевірка надісланого замовлення</h2><p>Повторне підтвердження використовує той самий запит і не створює дубль. Дані зафіксовані до отримання результату.</p><button type="button" className="btn outline" disabled={checking || submitting} onClick={recover}>{checking?'ПЕРЕВІРЯЄМО…':'ПЕРЕВІРИТИ РЕЗУЛЬТАТ'}</button></section>}
    {cartRequest?.error && !attempt && <div className="notice" role="alert">Не вдалося оновити ціни й наявність. Введені дані збережені.<button onClick={cartRequest.retry}>Спробувати ще раз</button></div>}
    {cartRequest?.loading && !attempt && <p role="status">Перевіряємо ціни й наявність…</p>}
    {!shownLines.length && !attempt && !blocked?<div className="commerce-panel"><h2>Кошик порожній</h2><p>Оберіть аромат, щоб оформити замовлення.</p><button className="btn primary" onClick={()=>go('/catalog')}>ДО КАТАЛОГУ</button></div>:<div className="checkout-layout"><form id="accord-checkout" onSubmit={submit} className="checkout-form" noValidate><fieldset className="checkout-fields" disabled={locked}>
      <section className="commerce-panel"><span className="step-label">01 / КОНТАКТИ</span><h2>Контактні дані</h2><div className="field-grid">
        <Field name="contact_surname" label="Прізвище" maxLength={64} value={form.contact_surname} onChange={value=>update('contact_surname',value)} autoComplete="family-name" error={errors.contact_surname}/>
        <Field name="contact_name" label="Ім’я" maxLength={128} value={form.contact_name} onChange={value=>update('contact_name',value)} autoComplete="given-name" error={errors.contact_name}/>
        <Field name="contact_patronymic" label="По батькові" maxLength={64} value={form.contact_patronymic} onChange={value=>update('contact_patronymic',value)} required={false} error={errors.contact_patronymic}/>
        <Field name="contact_phone" label="Номер телефону" maxLength={32} type="tel" value={form.contact_phone} onChange={value=>update('contact_phone',value)} autoComplete="tel" placeholder="+380XXXXXXXXX" error={errors.contact_phone}/>
      </div><p className="shop-hint">Вхід у Google не потрібний для покупки. Ми зв’яжемося за цим номером щодо замовлення.</p></section>
      <section className="commerce-panel"><span className="step-label">02 / ДОСТАВКА</span><h2>Доставка Новою поштою</h2>
        {np.courier_enabled && <div className="payment-methods">{[['warehouse','Відділення / поштомат'],['courier','Кур’єр']].map(([method,label])=><label key={method}><input name="delivery-method" type="radio" checked={form.delivery_method===method} onChange={()=>{update('delivery_method',method);update('address','');setWarehouseRef('');setWarehouseOptions([])}}/>{label}</label>)}</div>}
        <Field name="city" label="Місто / населений пункт" maxLength={128} autoComplete="address-level2" value={form.city} onChange={value=>{update('city',value);update('address','');setCityRef('');setSettlementRef('');setWarehouseRef('')}} placeholder="Почніть вводити місто" error={errors.city}/>
        {cityOptions.length>0 && <div className="suggestions" aria-label="Знайдені населені пункти">{cityOptions.slice(0,12).map(item=><button type="button" key={item.ref} onClick={()=>{update('city',item.label);update('address','');setCityRef(item.ref);setSettlementRef(item.settlement_ref || '');setWarehouseRef('');setCityOptions([]);document.getElementById('accord-address')?.focus()}}>{item.label}</button>)}</div>}
        <Field name="address" label={form.delivery_method==='courier'?'Адреса доставки':'Номер або адреса відділення / поштомата'} maxLength={255} autoComplete={form.delivery_method==='courier'?'street-address':'off'} value={form.address} onChange={value=>{update('address',value);setWarehouseRef('')}} placeholder={form.delivery_method==='courier'?'Вулиця, будинок, квартира':'Відділення №… або поштомат №…'} error={errors.address}/>
        {warehouseOptions.length>0 && <div className="suggestions" aria-label="Знайдені відділення">{warehouseOptions.slice(0,15).map(item=><button type="button" key={item.ref} onClick={()=>{update('address',item.label);setWarehouseRef(item.ref);setWarehouseOptions([])}}>{item.label}</button>)}</div>}
        {directoryBusy && <p className="shop-hint" role="status">Шукаємо {directoryBusy==='city'?'населений пункт':'відділення'}…</p>}
        <p className="shop-hint" role="status">{deliveryNote || 'Якщо потрібного варіанта немає в довіднику, введіть населений пункт і повну адресу вручну.'}</p>
      </section>
      <section className="commerce-panel"><span className="step-label">03 / ОПЛАТА</span><h2>Спосіб оплати</h2><div className="payment-methods"><label><input name="payment" type="radio" checked={form.payment_method==='cod'} onChange={()=>update('payment_method','cod')}/>Оплата при отриманні</label><label><input name="payment" type="radio" checked={form.payment_method==='card'} onChange={()=>update('payment_method','card')}/>Переказ за реквізитами після підтвердження менеджером</label></div><p className="shop-hint">Реквізити надає менеджер після підтвердження замовлення.</p><label className="shop-field"><span>Коментар до замовлення</span><textarea maxLength={500} rows={3} value={form.comment} onChange={event=>update('comment',event.target.value)} placeholder="Необов’язково"/></label></section>
      <section className="commerce-panel"><span className="step-label">04 / ПІДТВЕРДЖЕННЯ</span><h2>Перевірка замовлення</h2><div className="field-grid"><Field name="promo_code" label="Промокод" required={false} maxLength={64} value={form.promo_code} onChange={value=>update('promo_code',value)} error={errors.promo_code}/><div className="preview-button"><button type="button" className="btn outline" disabled={quoting || blocked} onClick={preview}>{quoting?'ПЕРЕРАХОВУЄМО…':'ПЕРЕРАХУВАТИ'}</button></div></div>
        {shop.account.has_session && Number(currentQuote?.bonus_available)>0 && <label className="checkbox-line"><input type="checkbox" checked={form.use_bonus} onChange={event=>update('use_bonus',event.target.checked)}/>Використати бонуси: до {money(currentQuote.bonus_available)} грн</label>}
        <label className="checkbox-line"><input name="terms_accepted" type="checkbox" checked={form.terms_accepted} required aria-invalid={errors.terms_accepted?true:undefined} aria-describedby={errors.terms_accepted?'checkout-terms-error':undefined} onChange={event=>update('terms_accepted',event.target.checked)}/>Погоджуюся з умовами покупки, доставки та обробкою персональних даних для оформлення й доставки замовлення</label>{errors.terms_accepted && <p className="field-error" id="checkout-terms-error">{errors.terms_accepted}</p>}
      </section></fieldset>
      {error && <div className="shop-error" role="alert" tabIndex={-1} ref={alert}>{error}</div>}
      <button type="submit" className="btn primary place-order" disabled={submitting || quoting || checking || (!attempt&&blocked)}>{submitting?'ОБРОБЛЯЄМО…':attempt?'ПОВТОРИТИ ПІДТВЕРДЖЕННЯ':currentQuote?'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ':'ПЕРЕВІРИТИ СУМУ'}</button>
    </form><aside className="order-summary"><h2>Ваші аромати</h2>{shownLines.map(({product,qty})=><div className="summary-line" key={product.id}><span>{product.brand && product.brand+' · '}{product.name}<small>{product.volume_ml ? product.volume_ml+' мл · ':''}{qty} шт.</small>{!attempt&&change && <span className="qty-control"><button type="button" aria-label={'Зменшити кількість '+product.name} onClick={()=>change(product.id,qty-1)}>−</button><span>{qty}</span><button type="button" aria-label={'Збільшити кількість '+product.name} disabled={qty>=product.stock || qty>=99} onClick={()=>change(product.id,qty+1)}>+</button><button type="button" onClick={()=>change(product.id,0)}>Прибрати</button></span>}</span><strong>{money(quoteLines.get(product.id)?.line_total ?? Number(product.price)*qty)} грн</strong></div>)}
      <div className="summary-total"><span>Товари</span><strong>{money(currentQuote?.subtotal ?? subtotal)} грн</strong></div>{currentQuote && <><div className="summary-total"><span>Знижка</span><strong>−{money(currentQuote.discount)} грн</strong></div><div className="summary-total"><span>Бонуси</span><strong>−{money(currentQuote.bonus_used)} грн</strong></div></>}
      <div className="summary-total final"><span>{attempt||currentQuote?'За товари':'Попередня сума'}</span><strong>{money(attempt?.total ?? currentQuote?.total ?? subtotal)} грн</strong></div><p>Доставка та послуга післяплати оплачуються окремо за тарифами перевізника. Сума за товари розраховується сервером.</p>{quoting && <p role="status">Оновлюємо підсумок…</p>}
    </aside></div>}
  </main>
}

export function CheckoutSuccess({result,go}) {
  if(!result?.order_id)return <main className="shell commerce-page"><h1>Перевірка замовлення</h1><div className="commerce-panel"><p>На цій сторінці немає підтвердження нової покупки. Перевірте історію замовлень у своєму профілі.</p><button className="btn primary" onClick={()=>go('/profile')}>ІСТОРІЯ ЗАМОВЛЕНЬ</button></div></main>
  return <main className="shell commerce-page success-page"><p className="eyebrow">ACCORD NICHE</p><h1>Дякуємо за замовлення</h1><div className="commerce-panel"><h2>Замовлення №{result.order_id} прийнято</h2><p>Менеджер опрацює його та зв’яжеться за вказаним номером телефону.</p><p className="order-success-total">За товари: <strong>{money(result.total)} грн</strong></p><p className="shop-hint">Це підтвердження створення замовлення. Статус оплати й доставки доступний у профілі цього браузера; для доступу з інших пристроїв увійдіть через Google.</p><div className="success-actions"><button className="btn primary" onClick={()=>go('/profile')}>ІСТОРІЯ ЗАМОВЛЕНЬ</button><button className="btn outline" onClick={()=>go('/catalog')}>ПРОДОВЖИТИ ПОКУПКИ</button></div></div></main>
}
