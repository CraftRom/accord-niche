import { useEffect, useRef, useState } from 'react'
import { checkoutCampaign, checkoutErrors, clearCheckoutAttempt, phoneNumber, readCheckoutAttempt, rememberCheckoutAttempt } from '../checkout'
import { useSuggestions } from './useSuggestions'
import { formatAmount } from '../format'
import { BUYER_INFO } from '../info'
import { Field } from '../ui/Field'

export const emptyCheckout=()=>({contact_surname:'',contact_name:'',contact_patronymic:'',contact_phone:'',city:'',address:'',delivery_method:'warehouse',payment_method:'cod',promo_code:'',comment:'',terms_accepted:false,use_bonus:false})

export function checkoutForm(payload={}) {
  const result=emptyCheckout()
  for(const name of Object.keys(result))if(payload[name]!=null)result[name]=payload[name]
  return result
}

export function CheckoutPage({site={},shop,cart,products,go,complete,cartRequest,change}) {
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
  const [summaryOpen,setSummaryOpen]=useState(false)
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
  const pickCity=item=>{update('city',item.label);update('address','');setCityRef(item.ref);setSettlementRef(item.settlement_ref || '');setWarehouseRef('');setCityOptions([]);document.getElementById('accord-address')?.focus()}
  const pickWarehouse=item=>{update('address',item.label);setWarehouseRef(item.ref);setWarehouseOptions([])}
  const citySuggest=useSuggestions('city',cityOptions.slice(0,12),pickCity,()=>setCityOptions([]))
  const warehouseSuggest=useSuggestions('address',warehouseOptions.slice(0,15),pickWarehouse,()=>setWarehouseOptions([]))
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
        <Field name="city" label="Місто / населений пункт" maxLength={128} autoComplete="address-level2" value={form.city} onChange={value=>{update('city',value);update('address','');setCityRef('');setSettlementRef('');setWarehouseRef('')}} placeholder="Почніть вводити місто" error={errors.city} inputProps={np.novaposhta_enabled?citySuggest.inputProps:{}}/>
        {citySuggest.listbox('Знайдені населені пункти')}
        <Field name="address" label={form.delivery_method==='courier'?'Адреса доставки':'Номер або адреса відділення / поштомата'} maxLength={255} autoComplete={form.delivery_method==='courier'?'street-address':'off'} value={form.address} onChange={value=>{update('address',value);setWarehouseRef('')}} placeholder={form.delivery_method==='courier'?'Вулиця, будинок, квартира':'Відділення №… або поштомат №…'} error={errors.address} inputProps={np.novaposhta_enabled&&form.delivery_method==='warehouse'?warehouseSuggest.inputProps:{}}/>
        {warehouseSuggest.listbox('Знайдені відділення')}
        {directoryBusy && <p className="shop-hint" role="status">Шукаємо {directoryBusy==='city'?'населений пункт':'відділення'}…</p>}
        <p className="shop-hint" role="status">{deliveryNote || 'Якщо потрібного варіанта немає в довіднику, введіть населений пункт і повну адресу вручну.'}</p>
      </section>
      <section className="commerce-panel"><span className="step-label">03 / ОПЛАТА</span><h2>Спосіб оплати</h2><div className="payment-methods"><label><input name="payment" type="radio" checked={form.payment_method==='cod'} onChange={()=>update('payment_method','cod')}/>Оплата при отриманні</label><label><input name="payment" type="radio" checked={form.payment_method==='card'} onChange={()=>update('payment_method','card')}/>Переказ за реквізитами після підтвердження менеджером</label></div><p className="shop-hint">Реквізити надає менеджер після підтвердження замовлення.</p><label className="shop-field"><span>Коментар до замовлення</span><textarea maxLength={500} rows={3} value={form.comment} onChange={event=>update('comment',event.target.value)} placeholder="Необов’язково"/></label></section>
      <section className="commerce-panel"><span className="step-label">04 / ПІДТВЕРДЖЕННЯ</span><h2>Перевірка замовлення</h2><div className="field-grid"><Field name="promo_code" label="Промокод" required={false} maxLength={64} value={form.promo_code} onChange={value=>update('promo_code',value)} error={errors.promo_code}/><div className="preview-button"><button type="button" className="btn outline" disabled={quoting || blocked} onClick={preview}>{quoting?'ПЕРЕРАХОВУЄМО…':'ПЕРЕРАХУВАТИ'}</button></div></div>
        {shop.account.has_session && Number(currentQuote?.bonus_available)>0 && <label className="checkbox-line"><input type="checkbox" checked={form.use_bonus} onChange={event=>update('use_bonus',event.target.checked)}/>Використати бонуси: до {formatAmount(currentQuote.bonus_available)} грн</label>}
        <label className="checkbox-line"><input name="terms_accepted" type="checkbox" checked={form.terms_accepted} required aria-invalid={errors.terms_accepted?true:undefined} aria-describedby={errors.terms_accepted?'checkout-terms-error':undefined} onChange={event=>update('terms_accepted',event.target.checked)}/>Погоджуюся з умовами покупки, доставки та обробкою персональних даних для оформлення й доставки замовлення</label>
        {/* W-10: what the consent refers to, readable without leaving the form. */}
        <div className="consent-docs">
          {['delivery','returns'].map(key=><details key={key}><summary>{BUYER_INFO[key][0]}</summary><p>{BUYER_INFO[key][1]}</p></details>)}
          {/* The documents open in a new tab so the filled form is kept. */}
          <p className="consent-links"><a href="/terms" target="_blank" rel="noopener">Публічна оферта</a><a href="/privacy" target="_blank" rel="noopener">Політика конфіденційності</a></p>
        </div>{errors.terms_accepted && <p className="field-error" id="checkout-terms-error">{errors.terms_accepted}</p>}
      </section></fieldset>
      {error && <div className="shop-error" role="alert" tabIndex={-1} ref={alert}>{error}</div>}
      <button type="submit" className="btn primary place-order" disabled={submitting || quoting || checking || (!attempt&&blocked)}>{submitting?'ОБРОБЛЯЄМО…':attempt?'ПОВТОРИТИ ПІДТВЕРДЖЕННЯ':currentQuote?'ПІДТВЕРДИТИ ЗАМОВЛЕННЯ':'ПЕРЕВІРИТИ СУМУ'}</button>
    </form><aside className="order-summary"><h2>Ваші аромати</h2>{/* W-08: on a phone the list folds into one line above the form. */}<button type="button" className="summary-toggle" aria-expanded={summaryOpen} aria-controls="checkout-summary-lines" onClick={()=>setSummaryOpen(open=>!open)}><span>{shownLines.reduce((sum,line)=>sum+line.qty,0)} шт. · {formatAmount(attempt?.total ?? currentQuote?.total ?? subtotal)} грн</span><span>{summaryOpen?'Сховати товари':'Показати товари'}</span></button><div id="checkout-summary-lines" className={'summary-lines'+(summaryOpen?' is-open':'')}>{shownLines.map(({product,qty})=><div className="summary-line" key={product.id}><span>{product.brand && product.brand+' · '}{product.name}<small>{product.volume_ml ? product.volume_ml+' мл · ':''}{qty} шт.</small>{!attempt&&change && <span className="qty-control"><button type="button" aria-label={'Зменшити кількість '+product.name} onClick={()=>change(product.id,qty-1)}>−</button><span>{qty}</span><button type="button" aria-label={'Збільшити кількість '+product.name} disabled={qty>=product.stock || qty>=99} onClick={()=>change(product.id,qty+1)}>+</button><button type="button" onClick={()=>change(product.id,0)}>Прибрати</button></span>}</span><strong>{formatAmount(quoteLines.get(product.id)?.line_total ?? Number(product.price)*qty)} грн</strong></div>)}</div>
      <div className="summary-total"><span>Товари</span><strong>{formatAmount(currentQuote?.subtotal ?? subtotal)} грн</strong></div>{currentQuote && <><div className="summary-total"><span>Знижка</span><strong>−{formatAmount(currentQuote.discount)} грн</strong></div><div className="summary-total"><span>Бонуси</span><strong>−{formatAmount(currentQuote.bonus_used)} грн</strong></div></>}
      <div className="summary-total final"><span>{attempt||currentQuote?'За товари':'Попередня сума'}</span><strong>{formatAmount(attempt?.total ?? currentQuote?.total ?? subtotal)} грн</strong></div><p>Доставка та послуга післяплати оплачуються окремо за тарифами перевізника. Сума за товари розраховується сервером.</p>{quoting && <p role="status">Оновлюємо підсумок…</p>}
    </aside></div>}
  </main>
}
