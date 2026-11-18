const ATTEMPT='accord:checkout:attempt'

export function phoneNumber(raw) {
  const digits=String(raw || '').replace(/[^0-9]/g,'')
  const body=digits.startsWith('380')?digits.slice(3):digits.startsWith('80')&&digits.length===11?digits.slice(2):digits.startsWith('0')&&digits.length===10?digits.slice(1):digits
  return /^[3-9][0-9]{8}$/.test(body)?'+380'+body:''
}

export function checkoutErrors(form) {
  const errors={}
  for(const [field,label,max] of [['contact_surname','Прізвище',64],['contact_name','Ім’я',128],['city','Населений пункт',128],['address',form.delivery_method==='courier'?'Адреса доставки':'Відділення або поштомат',255]]) {
    if(!form[field]?.trim())errors[field]='Заповніть поле «'+label+'».'
    else if(form[field].trim().length>max)errors[field]='Не більше '+max+' символів.'
  }
  if(!phoneNumber(form.contact_phone))errors.contact_phone='Вкажіть український номер, наприклад +380671234567.'
  if([form.contact_surname,form.contact_name,form.contact_patronymic].filter(Boolean).map(value=>value.trim()).join(' ').length>255)errors.contact_name='Скоротіть ПІБ: загалом не більше 255 символів.'
  if(!form.terms_accepted)errors.terms_accepted='Підтвердьте згоду з умовами покупки.'
  return errors
}

// Only an already-submitted request is retained, within this browser tab.
// A retry always uses its original payload and key, even after a reload.
export function readCheckoutAttempt() {
  try {
    const raw=sessionStorage.getItem(ATTEMPT)
    if(!raw || raw.length>65536)return null
    const value=JSON.parse(raw)
    if(!/^[A-Za-z0-9_-]{12,64}$/.test(value?.payload?.checkout_key || '') ||
       !/^[a-f0-9]{64}$/.test(value?.payload?.quote_token || '') || !Array.isArray(value.lines) || value.lines.length>30)return null
    for(const name of ['contact_surname','contact_name','contact_phone','city','address'])if(typeof value.payload[name]!=='string')return null
    for(const name of ['contact_patronymic','promo_code','comment'])if(value.payload[name]!=null && typeof value.payload[name]!=='string')return null
    if(!['warehouse','courier'].includes(value.payload.delivery_method) || !['cod','card'].includes(value.payload.payment_method) || value.payload.terms_accepted!==true)return null
    if(!value.lines.length || value.lines.some(line=>!Number.isSafeInteger(line?.product?.id) || typeof line.product.name!=='string' || !Number.isFinite(Number(line.product.price)) || !Number.isInteger(line.qty) || line.qty<1 || line.qty>99))return null
    return value
  }catch{return null}
}
export function rememberCheckoutAttempt(value) {try{sessionStorage.setItem(ATTEMPT,JSON.stringify(value))}catch{}}
export function clearCheckoutAttempt() {try{sessionStorage.removeItem(ATTEMPT)}catch{}}

export function campaignFromSearch(search) {
  const params=new URLSearchParams(search)
  if(!['source','medium','campaign','content','term'].some(key=>params.get('utm_'+key)?.trim()))return null
  return Object.fromEntries(['source','medium','campaign','content','term'].map(key=>[
    key,(params.get('utm_'+key) || (key==='source'?'accord_website':'')).replace(/[\u0000-\u001f]/g,'').trim().slice(0,key==='source'?80:160)]))
}
export function rememberCampaign(search) {try{const data=campaignFromSearch(search);if(data)sessionStorage.setItem('accord:campaign',JSON.stringify(data))}catch{}}
function storedCampaign() {
  try{
    const data=JSON.parse(sessionStorage.getItem('accord:campaign'))
    if(data && typeof data.source==='string')return Object.fromEntries(['source','medium','campaign','content','term'].map(key=>[key,String(data[key] || '').slice(0,key==='source'?80:160)]))
  }catch{}
  return {source:'accord_website',medium:'website',campaign:'',content:'',term:''}
}

// One anonymous first-party visit per browser tab (A07 funnel). Only a random
// id lives in sessionStorage: no cookie, nothing personal, gone with the tab.
const VISIT='accord:visit'
export function visitId(storage=sessionStorage, random=()=>crypto.randomUUID()) {
  try{
    const known=storage.getItem(VISIT)
    if(/^[A-Za-z0-9_-]{16,64}$/.test(known || ''))return known
    const fresh=String(random()).replaceAll('-','')
    storage.setItem(VISIT,fresh)
    return fresh
  }catch{return ''}
}

// Sends the visit once per tab. A failed POST is retried on the next route
// change; the server deduplicates, so a repeat never counts twice.
export async function recordVisit(send=fetch, storage=sessionStorage) {
  const id=visitId(storage)
  if(!id)return false
  try{if(storage.getItem(VISIT+':sent')===id)return true}catch{return false}
  try{
    const response=await send('/api/web/analytics/visit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:id,attribution:storedCampaign()}),keepalive:true,credentials:'same-origin'})
    if(!response.ok)return false
    try{storage.setItem(VISIT+':sent',id)}catch{}
    return true
  }catch{return false}
}

export function checkoutCampaign() {
  const id=visitId()
  return {...storedCampaign(),...(id?{session_id:id}:{})}
}
