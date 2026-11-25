import { SiteLink } from '../router'

// Perfume card: concentration, family and the notes pyramid. Search engines
// read the same values from JSON-LD; shoppers decide by them.
const CONCENTRATION = {parfum: 'Parfum', extrait: 'Extrait de Parfum', edp: 'Eau de Parfum', edt: 'Eau de Toilette',
  edc: 'Eau de Cologne', cologne: 'Cologne', oil: 'Парфумована олія'}

export function AromaDetails({group}) {
  const facts = [['Концентрація', CONCENTRATION[group.concentration]], ['Сімейство', group.fragrance_family],
    ['Парфумер', group.perfumer], ['Рік випуску', group.release_year]].filter(([, value]) => value)
  const notes = [['Верхні ноти', group.top_notes], ['Ноти серця', group.heart_notes], ['Базові ноти', group.base_notes]]
    .filter(([, value]) => value)
  if (!facts.length && !notes.length) return null
  return <section className="aroma-details" aria-labelledby="aroma-details-title"><h2 id="aroma-details-title">Про аромат</h2>
    {facts.length > 0 && <dl className="aroma-facts">{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
    {notes.length > 0 && <div className="aroma-notes"><h3>Піраміда нот</h3><dl>{notes.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></div>}
  </section>
}

export function Breadcrumbs({items, go}) {
  return <nav className="breadcrumbs shell" aria-label="Навігаційний ланцюжок"><ol>{items.map(([label, to], index) => <li key={label + index}>
    {to && index < items.length - 1 ? <SiteLink to={to} onNavigate={go}>{label}</SiteLink> : <span aria-current="page">{label}</span>}</li>)}</ol></nav>
}
