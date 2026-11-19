export function PageTitle({label, title, detail}) {
  return <div className="page-title shell"><p className="eyebrow">{label}</p><h1>{title}</h1>{detail && <p>{detail}</p>}</div>
}
