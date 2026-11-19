// W-35: one icon scale — 20 px for header and dialog actions, 18 px inline —
// all with the same 1.5 stroke, so the header icons line up optically.
export function Icon({name, size = 20}) {
  const props = {width:size, height:size, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', strokeWidth:1.5, strokeLinecap:'round', strokeLinejoin:'round', 'aria-hidden':true}
  if (name === 'search') return <svg {...props}><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></svg>
  if (name === 'user') return <svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4.5 21c0-4 3.2-6 7.5-6s7.5 2 7.5 6"/></svg>
  if (name === 'bag') return <svg {...props}><path d="M4 8h16l-1.2 13H5.2L4 8Z"/><path d="M9 9V6a3 3 0 0 1 6 0v3"/></svg>
  if (name === 'close') return <svg {...props}><path d="m5 5 14 14M19 5 5 19"/></svg>
  if (name === 'menu') return <svg {...props}><path d="M3 7h18M3 12h18M3 17h18"/></svg>
  return <svg {...props}><path d="M4 12h16m-7-7 7 7-7 7"/></svg>
}
