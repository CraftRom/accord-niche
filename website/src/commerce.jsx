import { useCallback, useEffect, useRef, useState } from 'react'

const money = (amount) => new Intl.NumberFormat('uk-UA', { maximumFractionDigits:2 }).format(Number(amount || 0))

async function parseResponse(response) {
  const payload = await response.json().catch(()=>({}))
  if (!response.ok) {
    const raw = payload?.detail
    throw new Error(typeof raw === 'string' ? raw :
      Array.isArray(raw) ? raw.map(x=>x.msg).join('; ') : `Не вдалося виконати запит (${response.status})`)
  }
  return payload
}

export function useCommerce() {
  const [account, setAccount] = useState({ signed_in:false, has_session:false })
  const [googleClient, setGoogleClient] = useState('')
  const [smsEnabled, setSmsEnabled] = useState(false)
  const [ready, setReady] = useState(false)
  const csrfRef = useRef('')
  const loadSession = useCallback(async () => {
    const payload = await parseResponse(await fetch('/api/web/session', {credentials:'include',cache:'no-store'}))
    csrfRef.current = payload.csrf
    setAccount(payload.account)
    setGoogleClient(payload.google_client_id || '')
    setSmsEnabled(Boolean(payload.phone_verification_enabled))
    setReady(true)
    return payload
  }, [])
  useEffect(()=>{loadSession().catch(()=>setReady(true))},[loadSession])
  const request = useCallback(async (endpoint, method='GET', data) => {
    if (!csrfRef.current) await loadSession()
    const response = await fetch(`/api/web${endpoint}`, {
      method, credentials:'include', cache:'no-store',
      headers: {...(method !== 'GET' ? {'Content-Type':'application/json','X-CSRF-Token':csrfRef.current}: {})},
      ...(data !== undefined ? {body:JSON.stringify(data)} : {}),
    })
    return parseResponse(response)
  },[loadSession])
  return {account, googleClient, smsEnabled, ready, refresh:loadSession, request}
}

function Field({name, label, value, onChange, required=true, type='text', placeholder='', autoComplete, maxLength}) {
  return <label className="shop-field"><span>{label}{required ? ' *' : ''}</span><input name={name} type={type} value={value} required={required}
    maxLength={maxLength} placeholder={placeholder} autoComplete={autoComplete} onChange={e=>onChange(e.target.value)} /></label>
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

function OrderList({orders,loading,cancelOrder}) {
  if(loading) return <p className="shop-hint">Завантаження історії замовлень…</p>
  if(!orders.length) return <div className="shop-empty">Історія покупок поки порожня.</div>
  return <div className="order-list">{orders.map(o=><article className="order-record" key={o.id}>
    <div className="order-record-head"><div><strong>Замовлення №{o.id}</strong><span>{o.created_at ? new Date(o.created_at).toLocaleDateString('uk-UA') : ''}</span></div><strong>{money(o.total)} грн</strong></div>
    <p className="order-status">{o.status_label || o.crm_status_name || o.status}</p>
    <ul>{(o.items||[]).map((item,i)=><li key={i}>{item.name} × {item.qty}<span>{money(Number(item.price)*Number(item.qty))} грн</span></li>)}</ul>
    {o.tracking_number && <p>ТТН: <strong>{o.tracking_number}</strong></p>}
    {o.operator_name && <p>Менеджер: {o.operator_name}</p>}
    {o.can_cancel && <button className="text-muted-button" onClick={()=>cancelOrder(o.id)}>Скасувати замовлення</button>}
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
  const [saving,setSaving]=useState(false)
  const refreshOrders=()=>{
    setLoading(true)
    Promise.all([shop.request('/orders?limit=30&offset=0'),shop.request('/profile')])
      .then(([result,data])=>{setOrders(result.items||[]);setHasMore(Boolean(result.has_more));setProfile(data)})
      .catch(e=>setError(e.message)).finally(()=>setLoading(false))
  }
  const loadMore=async()=>{
    if(moreLoading || !hasMore)return
    setMoreLoading(true)
    try{const result=await shop.request(`/orders?limit=30&offset=${orders.length}`)
      setOrders(prev=>[...prev,...(result.items||[])]);setHasMore(Boolean(result.has_more))}
    catch(e){setError(e.message)}finally{setMoreLoading(false)}
  }
  useEffect(()=>{if(shop.account.has_session)refreshOrders();else setLoading(false)},[shop.account.has_session,shop.account.signed_in,shop.account.telegram_linked])
  const save=async()=>{setSaving(true);setError('');try{await shop.request('/profile','PATCH',{display_name:newName});await shop.refresh();setNewName('')}catch(e){setError(e.message)}finally{setSaving(false)}}
  const logout=async()=>{setError('');try{await shop.request('/auth/logout','POST');await shop.refresh();setOrders([]);setProfile(null)}catch(e){setError(e.message)}}
  const cancelOrder=async id=>{
    if (!window.confirm(`Скасувати замовлення №${id}? Після скасування потрібно буде оформити нове.`)) return
    setError('')
    try{await shop.request(`/orders/${id}/cancel`,'POST');refreshOrders()}
    catch(e){setError(e.message)}
  }
  return <main className="shell commerce-page">
    <p className="eyebrow">ОСОБИСТИЙ КАБІНЕТ</p><h1>Мій профіль</h1>
    {!shop.account.signed_in ? <section className="commerce-panel">
      <h2>Увійди через Google</h2><p>Усі замовлення в одному місці. Вхід не потрібен для покупки — можна замовити як гість.</p>
      <GoogleLogin shop={shop} />
    </section> : <section className="commerce-panel">
      <h2>{shop.account.name || 'Покупець'}</h2><p>{shop.account.email}</p>
      <div className="profile-edit"><Field name="displayName" label="Змінити імʼя" required={false} value={newName} onChange={setNewName} placeholder="Твоє імʼя" />
        <button className="btn outline" disabled={!newName.trim() || saving} onClick={save}>ЗБЕРЕГТИ</button></div>
      {profile && <div className="profile-facts">
        <div><span>Усього замовлень</span><strong>{profile.orders_count}</strong></div>
        <div><span>Бонуси сайту</span><strong>{money(profile.bonus_balance)} грн</strong></div>
        {profile.latest_delivery?.city && <div><span>Остання доставка</span><strong>{profile.latest_delivery.city}, {profile.latest_delivery.address}</strong></div>}
      </div>}
      <PhoneVerification shop={shop} refreshOrders={refreshOrders}/>
      <TelegramHistoryLink shop={shop} refreshOrders={refreshOrders}/>
      <button className="text-muted-button" onClick={logout}>Вийти з профілю</button>
    </section>}
    <section className="orders-section"><div className="section-row"><h2>Історія покупок</h2><button className="text-muted-button" onClick={refreshOrders} disabled={!shop.account.has_session}>Оновити</button></div>
      {error && <p className="shop-error" role="alert">{error}</p>}
      {shop.account.has_session ? <><OrderList orders={orders} loading={loading} cancelOrder={cancelOrder} />{hasMore && !loading && <button className="btn outline" disabled={moreLoading} onClick={loadMore}>{moreLoading?'ЗАВАНТАЖУЄМО…':'ПОКАЗАТИ БІЛЬШЕ ЗАМОВЛЕНЬ'}</button>}</> : <div className="shop-empty">Після першого замовлення історія зʼявиться тут. Для збереження між пристроями увійди через Google.</div>}
    </section><button className="btn outline" onClick={()=>go('/catalog')}>ПРОДОВЖИТИ ПОКУПКИ</button>
  </main>
}

export function CheckoutPage({shop,cart,products,go,complete}) {
  const lines=Object.entries(cart).map(([id,qty])=>({product:products.find(p=>p.id===Number(id)),qty:Number(qty)}))
    .filter(x=>x.product && x.qty>0)
  const total=lines.reduce((s,x)=>s+Number(x.product.price)*x.qty,0)
  const [form,setForm]=useState({contact_surname:'',contact_name:'',contact_patronymic:'',contact_phone:'',city:'',address:'',
    delivery_method:'warehouse',payment_method:'cod',promo_code:'',comment:'',terms_accepted:false,use_bonus:false})
  const [quote,setQuote]=useState(null)
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')
  const [np,setNp]=useState({courier_enabled:false,novaposhta_enabled:false})
  const [cityOptions,setCityOptions]=useState([])
  const [warehouseOptions,setWarehouseOptions]=useState([])
  const [cityRef,setCityRef]=useState('')
  const [settlementRef,setSettlementRef]=useState('')
  const [warehouseRef,setWarehouseRef]=useState('')
  const checkoutKey=useRef('')
  const update=(field,value)=>{setForm(prev=>({...prev,[field]:value}));if(['promo_code','use_bonus'].includes(field))setQuote(null)}
  useEffect(()=>{shop.request('/delivery/config').then(setNp).catch(()=>{})},[])
  useEffect(()=>{
    if (!shop.account.has_session) return
    shop.request('/checkout/defaults').then(data=>{
      setForm(prev=>{
        // Never overwrite inputs the shopper has already started typing.
        if (prev.contact_name || prev.contact_phone || prev.city || prev.address) return prev
        return {...prev, contact_surname:data.contact_surname||'',
          contact_name:data.contact_name||'', contact_patronymic:data.contact_patronymic||'',
          contact_phone:data.contact_phone||'', city:data.city||'',address:data.address||'',
          delivery_method:data.delivery_method||'warehouse',payment_method:data.payment_method||'cod'}
      })
      if(data.delivery_city_ref)setCityRef(data.delivery_city_ref)
      if(data.delivery_warehouse_ref)setWarehouseRef(data.delivery_warehouse_ref)
    }).catch(()=>{})
  },[shop.account.has_session])
  useEffect(()=>{
    if (!np.novaposhta_enabled || cityRef || form.city.trim().length<2) {setCityOptions([]);return}
    const timer=setTimeout(()=>shop.request(`/delivery/cities?q=${encodeURIComponent(form.city)}`).then(result=>setCityOptions(result.items||[])).catch(()=>setCityOptions([])),400)
    return ()=>clearTimeout(timer)
  },[np.novaposhta_enabled,form.city,cityRef])
  useEffect(()=>{
    if(!np.novaposhta_enabled || (!cityRef && !settlementRef)){setWarehouseOptions([]);return}
    const timer=setTimeout(()=>shop.request(`/delivery/warehouses?city_ref=${encodeURIComponent(cityRef)}&settlement_ref=${encodeURIComponent(settlementRef)}&q=${encodeURIComponent(form.address)}`)
      .then(result=>setWarehouseOptions(result.items||[])).catch(()=>setWarehouseOptions([])),350)
    return ()=>clearTimeout(timer)
  },[np.novaposhta_enabled,cityRef,settlementRef,form.address])
  const items=lines.map(({product,qty})=>({product_id:product.id,qty}))
  async function preview(){
    setLoading(true);setError('')
    try {
      const result=await shop.request('/checkout/quote','POST',{items,promo_code:form.promo_code.trim()||null,
        use_bonus:form.use_bonus,terms_accepted:form.terms_accepted})
      setQuote(result);await shop.refresh();return result
    } catch(e){setQuote(null);setError(e.message);return null}finally{setLoading(false)}
  }
  async function submit(event){
    event.preventDefault()
    if (!lines.length || loading) return
    if (!checkoutKey.current) checkoutKey.current=crypto.randomUUID().replaceAll('-','')
    const fresh=await preview()
    if (!fresh) return
    setLoading(true);setError('')
    try {
      const payload={
        contact_surname:form.contact_surname.trim(),contact_name:form.contact_name.trim(),
        contact_patronymic:form.contact_patronymic.trim()||null,contact_phone:form.contact_phone.trim(),
        city:form.city.trim(),address:form.address.trim(),delivery_method:form.delivery_method,
        delivery_city_ref:cityRef||null,delivery_warehouse_ref:warehouseRef||null,
        payment_method:form.payment_method,comment:form.comment.trim()||null,
        promo_code:form.promo_code.trim()||null,use_bonus:form.use_bonus,
        quote_token:fresh.quote_token,checkout_key:checkoutKey.current,terms_accepted:form.terms_accepted,
      }
      const result=await shop.request('/checkout','POST',payload)
      complete(result)
      checkoutKey.current=''
      go('/order/success')
    } catch(e){setError(e.message)}finally{setLoading(false)}
  }
  return <main className="shell commerce-page"><button className="back-link" onClick={()=>go('/catalog')}>← Повернутися в каталог</button>
    <p className="eyebrow">ОФОРМЛЕННЯ ПОКУПКИ</p><h1>Ваше замовлення</h1>
    {!lines.length ? <div className="commerce-panel"><h2>Кошик порожній</h2><p>Оберіть аромат, щоб оформити замовлення.</p><button className="btn primary" onClick={()=>go('/catalog')}>ДО КАТАЛОГУ</button></div>
    : <div className="checkout-layout"><form id="accord-checkout" onSubmit={submit} className="checkout-form">
        <section className="commerce-panel"><span className="step-label">01 / КОНТАКТИ</span><h2>Контактні дані</h2>
          <div className="field-grid"><Field name="surname" label="Прізвище" value={form.contact_surname} onChange={v=>update('contact_surname',v)} autoComplete="family-name"/>
          <Field name="name" label="Імʼя" value={form.contact_name} onChange={v=>update('contact_name',v)} autoComplete="given-name"/>
          <Field name="patronymic" label="По батькові" value={form.contact_patronymic} onChange={v=>update('contact_patronymic',v)} required={false}/>
          <Field name="phone" label="Номер телефону" value={form.contact_phone} onChange={v=>update('contact_phone',v)} type="tel" placeholder="+380XXXXXXXXX" autoComplete="tel"/></div>
          <p className="shop-hint">Ми звʼяжемося за цим номером щодо замовлення. Вхід у Google не обовʼязковий.</p>
        </section>
        <section className="commerce-panel"><span className="step-label">02 / ДОСТАВКА</span><h2>Доставка Новою поштою</h2>
          {np.courier_enabled && <div className="payment-methods"><label><input type="radio" checked={form.delivery_method==='warehouse'} onChange={()=>update('delivery_method','warehouse')}/> Відділення / поштомат</label>
            <label><input type="radio" checked={form.delivery_method==='courier'} onChange={()=>update('delivery_method','courier')}/> Курʼєр</label></div>}
          <Field name="city" label="Місто / населений пункт" value={form.city} onChange={v=>{update('city',v);setCityRef('');setSettlementRef('');setWarehouseRef('')}} placeholder="Почніть вводити місто"/>
          {cityOptions.length>0 && <div className="suggestions" role="listbox">{cityOptions.slice(0,8).map(item=><button key={item.ref} type="button" onClick={()=>{update('city',item.label);setCityRef(item.ref);setSettlementRef(item.settlement_ref||'');setCityOptions([])}}>{item.label}</button>)}</div>}
          <Field name="warehouse" label={form.delivery_method==='courier'?'Адреса доставки':'Номер або адреса відділення / поштомата'}
            value={form.address} onChange={v=>{update('address',v);setWarehouseRef('')}} placeholder={form.delivery_method==='courier'?'Вулиця, будинок, квартира':'Відділення №… або поштомат №…'}/>
          {warehouseOptions.length>0 && <div className="suggestions" role="listbox">{warehouseOptions.slice(0,10).map(item=><button key={item.ref} type="button" onClick={()=>{update('address',item.label);setWarehouseRef(item.ref);setWarehouseOptions([])}}>{item.label}</button>)}</div>}
          <p className="shop-hint">Якщо довідник Нової пошти недоступний, можна ввести місто та відділення вручну.</p>
        </section>
        <section className="commerce-panel"><span className="step-label">03 / ОПЛАТА</span><h2>Спосіб оплати</h2>
          <div className="payment-methods"><label><input type="radio" checked={form.payment_method==='cod'} onChange={()=>update('payment_method','cod')}/> Оплата при отриманні (накладений платіж)</label>
          <label><input type="radio" checked={form.payment_method==='card'} onChange={()=>update('payment_method','card')}/> Переказ за реквізитами після підтвердження менеджером</label></div>
          <p className="shop-hint">Оплата онлайн банківською карткою не підключена. Не переказуйте гроші до отримання підтвердження й реквізитів від магазину.</p>
          <label className="shop-field"><span>Коментар до замовлення</span><textarea rows="3" maxLength="500" value={form.comment} onChange={e=>update('comment',e.target.value)} placeholder="Побажання до замовлення (необовʼязково)"/></label>
        </section>
        <section className="commerce-panel"><span className="step-label">04 / ПІДТВЕРДЖЕННЯ</span><h2>Перевірка замовлення</h2>
          <div className="field-grid"><Field name="promo" label="Промокод" value={form.promo_code} onChange={v=>update('promo_code',v)} required={false} placeholder="Якщо маєте" maxLength={64}/>
          <div className="preview-button"><button type="button" className="btn outline" disabled={loading || !form.terms_accepted} onClick={preview}>ПЕРЕРАХУВАТИ</button></div></div>
          {shop.account.signed_in && <label className="checkbox-line"><input type="checkbox" checked={form.use_bonus} onChange={e=>update('use_bonus',e.target.checked)}/> Використати доступні бонуси</label>}
          <label className="checkbox-line"><input type="checkbox" required checked={form.terms_accepted} onChange={e=>update('terms_accepted',e.target.checked)}/> Погоджуюся з умовами покупки, доставки та обробкою персональних даних</label>
          <p className="shop-hint">Натискаючи «Підтвердити замовлення», погоджуюся на обробку контактних даних для оформлення та доставки покупки.</p>
        </section>
        {error && <div className="shop-error" role="alert">{error}</div>}
        <button type="submit" className="btn primary place-order" disabled={loading || !form.terms_accepted}>{loading?'ОБРОБЛЯЄМО…':'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ'}</button>
      </form>
      <aside className="order-summary"><h2>Твої аромати</h2>{lines.map(({product,qty})=><div className="summary-line" key={product.id}><span>{product.brand} · {product.name}<small>{product.volume_ml} мл × {qty}</small></span><strong>{money(Number(product.price)*qty)} грн</strong></div>)}
        <div className="summary-total"><span>Товари</span><strong>{money(total)} грн</strong></div>
        {quote && <><div className="summary-total"><span>Знижка</span><strong>−{money(quote.discount)} грн</strong></div><div className="summary-total"><span>Бонуси</span><strong>−{money(quote.bonus_used)} грн</strong></div></>}
        <div className="summary-total final"><span>До сплати</span><strong>{money(quote?.total ?? total)} грн</strong></div><p>Доставка оплачується за тарифами перевізника. Остаточна сума за товари перевіряється сервером перед підтвердженням.</p>
      </aside>
    </div>}
  </main>
}

export function CheckoutSuccess({result,go}) {
  return <main className="shell commerce-page success-page"><p className="eyebrow">ACCORD NICHE</p><h1>Дякуємо за замовлення</h1>
    <div className="commerce-panel"><h2>{result?.order_id ? `Замовлення №${result.order_id} прийнято` : 'Ваші покупки'}</h2>
      <p>Замовлення збережено в спільній системі магазину. Менеджер опрацює його та звʼяжеться за вказаним номером телефону.</p>
      {result && <p className="order-success-total">До сплати за товари: <strong>{money(result.total)} грн</strong></p>}
      <p className="shop-hint">Це не підтвердження оплати. Ви зможете переглядати статус у профілі цього браузера; для доступу з інших пристроїв увійдіть через Google.</p>
      <div className="success-actions"><button className="btn primary" onClick={()=>go('/profile')}>ІСТОРІЯ ЗАМОВЛЕНЬ</button><button className="btn outline" onClick={()=>go('/catalog')}>ПРОДОВЖИТИ ПОКУПКИ</button></div>
    </div>
  </main>
}
