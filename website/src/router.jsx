import { useEffect, useState } from 'react'
import { withViewTransition } from './motion'

export const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')

export function useRoute() {
  const read = () => (location.pathname.slice(BASE.length) || '/') + location.search
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const pop = () => withViewTransition(() => setRoute(read()))
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])
  function go(to, options = {}) {
    const next = BASE + to
    if (location.pathname + location.search !== next) history[options.replace ? 'replaceState' : 'pushState'](null, '', next)
    // A new page cross-fades; switching a volume on the same page does not.
    const apply = () => {
      setRoute(to)
      if (options.scroll !== false) window.scrollTo({top: 0, behavior: 'instant'})
    }
    if (options.scroll === false) apply(); else withViewTransition(apply)
  }
  return [route, go]
}

/**
 * W-05: navigation is a real link. A plain left click stays an in-app
 * transition; Ctrl/Cmd/Shift/Alt-click, the middle button and the context menu
 * keep their native behaviour (new tab, copy address), and the address is
 * visible to the browser and to crawlers.
 */
export function SiteLink({to, onNavigate, current = false, children, ...rest}) {
  const follow = event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    onNavigate(to)
  }
  return <a href={(BASE || '') + to} onClick={follow} aria-current={current ? 'page' : undefined} {...rest}>{children}</a>
}
