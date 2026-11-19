import { useCallback, useEffect, useRef, useState } from 'react'
import { clearCheckoutAttempt } from '../checkout'

export async function parseResponse(response) {
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

export async function customerFetch(url,options={}) {
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
  const [telegramPhone, setTelegramPhone] = useState(false)
  const [ready, setReady] = useState(false)
  const csrfRef = useRef('')
  const sessionRequest=useRef(null)
  const loadSession = useCallback(() => {
    if(sessionRequest.current)return sessionRequest.current
    sessionRequest.current=customerFetch('/api/web/session',{credentials:'include',cache:'no-store'})
      .then(payload=>{
        csrfRef.current=payload.csrf;setAccount(payload.account)
        setGoogleClient(payload.google_client_id || '');setSmsEnabled(Boolean(payload.phone_sms_enabled));setTelegramPhone(Boolean(payload.phone_telegram_enabled));setReady(true)
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
  return {account, googleClient, smsEnabled, telegramPhone, ready, refresh:loadSession, request}
}
