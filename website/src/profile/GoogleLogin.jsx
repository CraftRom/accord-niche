import { useEffect, useRef, useState } from 'react'

export function GoogleLogin({ shop }) {
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
