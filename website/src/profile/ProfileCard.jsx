// W-22: each card says what it is for and its state in words.
export const STATUS_TEXT={ok:'Підключено',warn:'Потрібне підтвердження',off:'Не підключено'}

export function ProfileCard({title,status,children}) {
  const [tone,label]=status || []
  return <section className="profile-card" aria-label={title}><div className="profile-card-head"><h3>{title}</h3>{tone && <span className={'status-chip '+tone}>{label || STATUS_TEXT[tone]}</span>}</div>{children}</section>
}
