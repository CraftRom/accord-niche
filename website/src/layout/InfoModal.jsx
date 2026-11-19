import { useRef } from 'react'
import { BUYER_INFO } from '../info'
import { Icon } from '../ui/Icon'
import { useDialog } from '../useDialog'

export function InfoModal({name, close, site}) {
  const dialog=useRef(null)
  useDialog(dialog,Boolean(name),close)
  const content = BUYER_INFO
  if (!name) return null
  return <div className="modal-mask" onMouseDown={event => {if (event.target === event.currentTarget) close()}}><section ref={dialog} tabIndex={-1} className="info-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><button className="icon-btn modal-close" onClick={close} aria-label="Закрити"><Icon name="close"/></button><p className="eyebrow">ACCORD NICHE</p><h2 id="modal-title">{content[name]?.[0]}</h2><p>{content[name]?.[1]}</p>{site.phone && <p>{site.phone}</p>}{site.email && <p>{site.email}</p>}<button className="btn outline" onClick={close}>Зрозуміло</button></section></div>
}
