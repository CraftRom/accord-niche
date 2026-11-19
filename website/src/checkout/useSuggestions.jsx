import { useEffect, useState } from 'react'

/**
 * W-09: Nova Poshta suggestions as a combobox. Arrow keys move through the
 * list, Enter picks the highlighted entry (without submitting the order),
 * Escape closes the list and keeps what was typed. Pointer users click as
 * before; options stay buttons so nothing else changes for them.
 */
export function useSuggestions(name, options, pick, close) {
  const [active, setActive] = useState(-1)
  const list = 'accord-' + name + '-list'
  // A new search result resets the highlight; re-rendering the same list does not.
  const key = options.map(item => item.ref).join('|')
  useEffect(() => setActive(-1), [key])
  const onKeyDown = event => {
    if (!options.length) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive(current => (current + step + options.length) % options.length)
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault()
      pick(options[active])
    } else if (event.key === 'Escape') {
      event.preventDefault()
      close()
    }
  }
  const inputProps = {role:'combobox', 'aria-autocomplete':'list', 'aria-expanded':options.length > 0, 'aria-controls':list,
    'aria-activedescendant':active >= 0 ? list + '-' + active : undefined, onKeyDown}
  const listbox = label => options.length > 0 && <div className="suggestions" id={list} role="listbox" aria-label={label}>{options.map((item, index) =>
    <button type="button" role="option" tabIndex={-1} id={list + '-' + index} key={item.ref} aria-selected={index === active} className={index === active ? 'active' : undefined}
      onMouseDown={event => event.preventDefault()} onClick={() => pick(item)}>{item.label}</button>)}</div>
  return { inputProps, listbox }
}
