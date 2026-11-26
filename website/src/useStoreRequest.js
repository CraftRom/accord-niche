import { useEffect, useState } from 'react'

/** One request at a time; abort old searches and retain data only for this URL. */
export function useStoreRequest(url, interval = 60000) {
  const [state, setState] = useState({url: null, data: null, loading: false, error: ''})
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    if (!url) return
    let disposed = false, running = false, controller
    async function read() {
      if (running) return
      running = true
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 12000)
      setState(old => ({url, data: old.url === url ? old.data : null, loading: true, error: ''}))
      try {
        const response = await fetch(url, {signal: controller.signal, cache: 'no-store'})
        if(!response.ok){
          const error=new Error([404,410].includes(response.status)?'Товар більше недоступний.':response.status===422?'Некоректні параметри відбору. Скиньте фільтри та повторіть пошук.':'Не вдалося отримати дані магазину. Спробуйте ще раз.')
          error.status=response.status
          throw error
        }
        const data = await response.json()
        // Answered from the test-mode sandbox (the site-wide test mode).
        const sandbox = response.headers?.get?.('x-accord-test-mode') === '1'
        if (!disposed) setState({url, data, sandbox, loading: false, error: ''})
      } catch (error) {
        if (!disposed) setState(old => ({...old,url,data:[404,410].includes(error.status)?null:old.data,
          loading:false,errorStatus:error.status || 0,error:error.name==='AbortError'?'Сервер відповідає надто довго. Спробуйте ще раз.':error.message}))
      } finally {
        clearTimeout(timeout)
        running = false
      }
    }
    read()
    const timer = interval ? setInterval(() => {if (!document.hidden) read()}, interval) : null
    const visible = () => {if (!document.hidden) read()}
    window.addEventListener('online', visible)
    document.addEventListener('visibilitychange', visible)
    return () => {disposed = true; controller?.abort(); clearInterval(timer); window.removeEventListener('online', visible); document.removeEventListener('visibilitychange', visible)}
  }, [url, revision, interval])
  return {...(state.url === url ? state : {data: null, loading: Boolean(url), error: ''}), retry: () => setRevision(value => value + 1)}
}
