import {useEffect, useState} from 'react'
import {Link, NavLink, Navigate, useParams} from 'react-router-dom'
import {api} from '../api'
import './storeAudit.css'

const views = {
  seo:'SEO-проблеми', catalog:'Каталог і товарні сторінки', orders:'Корзина та замовлення',
  profile:'Профіль і історія покупок', delivery:'Nova Poshta', dashboard:'Dashboard',
  miniapp:'Mini App', domains:'DNS і домени', security:'Безпека', manual:'Потребує ручної перевірки',
  fixed:'Виправлено', blockers:'Блокери релізу', release:'Готовність релізу',
}
const modules = {...Object.fromEntries(Object.entries(views).slice(0,9)), blog:'Блог і модерація',
  bot:'Telegram-бот', api:'API', database:'База даних', redis:'Redis', nginx:'Nginx', certbot:'Certbot'}
const states = {open:'Відкрито', working:'У роботі', retest:'Очікує повторного тесту', failed:'Підтверджена помилка',
  inconclusive:'Тест без висновку', verified:'Перевірено повторно', fixed:'Виправлено'}
const outcomes = {pass:'Успішно', fail:'Помилка', unknown:'Без підтвердження'}
const types = {auto:'Автоматична', manual:'Ручна'}
const assessments = {confirmed:'Підтверджені помилки', risk:'Потенційні ризики', assumption:'Неперевірені припущення', verified:'Підтверджено тестом'}
const fields = {title:'Назва задачі', route:'URL або маршрут', keyword:'Запит або ключове слово',
  expected:'Очікуваний результат', symptom:'Симптом', steps:'Кроки відтворення', risk:'Ризик',
  dependencies:'Залежності', team:'Команда виправлення', link:'Посилання на коміт або задачу', competitor:'URL конкурентної сторінки'}
const empty = {...Object.fromEntries(Object.keys(fields).map(k=>[k,''])), module:'seo', priority:'P1',
  assessment:'assumption', workflow:'open'}
const envs = {production:'Продакшн', staging:'Тестовий стенд', local:'Локальне'}
const rank = r => r.status === 'failed' ? 'confirmed' : ['fixed','verified'].includes(r.status) ? 'verified' : r.details.assessment
const time = date => date ? new Date(date).toLocaleString('uk-UA') : 'Ще не перевірено'
function Select({label, options, value, onChange, all=false, disabled=false}) {
  return <label>{label}<select value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>
    {all && <option value="">Усі</option>}{Object.entries(options).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
}
const priority = Object.fromEntries(['P0','P1','P2','P3'].map(p=>[p,p]))

function Comparison({value}) {
  if(!value) return null
  return <div className="audit-grid"><div><h4>ACCORD NICHE</h4><p>{value.store}</p></div>
    <div><h4>Конкурентна сторінка</h4><p>{value.rival}</p></div></div>
}

function Editor({row, env, close, refresh}) {
  const [d,setD] = useState(row?.details || empty)
  const [result,setResult] = useState('')
  const [actual,setActual] = useState('')
  const [log,setLog] = useState('')
  const [comparison,setComparison] = useState({store:'',rival:''})
  const [history,setHistory] = useState(null)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const update = (k,v)=>setD(prev=>({...prev,[k]:v}))
  const dirty = row && JSON.stringify(row.details)!==JSON.stringify(d)
  async function act(fn) {
    setBusy(true); setError('')
    try { await fn() } catch(e) { setError(e.message) } finally { setBusy(false) }
  }
  function save(e) {
    e.preventDefault()
    act(async()=>{
      const saved = row ? await api.storeAudit.edit(env,row.id,{version:row.version,details:d}) : await api.storeAudit.create(env,d)
      await refresh(saved.id)
    })
  }
  function run(e) {
    e.preventDefault()
    act(async()=>{
      const body = row.type==='auto' ? {} : {outcome:result,actual,log}
      if (row.id.startsWith('benchmark')) body.comparison=comparison
      await api.storeAudit.test(env,row.id,{version:row.version,...body})
      await refresh(row.id)
    })
  }
  function loadHistory(more=false) {
    act(async()=>{
      const page=await api.storeAudit.history(env,row.id,more ? history.at(-1).row.version : undefined)
      setHistory(more ? [...history,...page] : page)
    })
  }
  return <section className="card audit-editor"><header><h2>{row?.details.title || 'Нова задача'}</h2>
    <button className="btn ghost" disabled={busy} onClick={close}>Закрити</button></header>
    {error && <p role="alert">{error} {row && <button className="btn ghost" onClick={()=>act(()=>refresh(row.id))}>Оновити запис</button>}</p>}
    <fieldset disabled={busy}><form onSubmit={save}>
      <div className="audit-grid"><Select label="Модуль" options={modules} value={d.module} disabled={row?.type==='auto'} onChange={v=>update('module',v)}/>
      <Select label="Пріоритет" options={priority} value={d.priority} onChange={v=>update('priority',v)}/>
      <Select label="Оцінка до перевірки" options={{risk:assessments.risk,assumption:assessments.assumption}} value={d.assessment} onChange={v=>update('assessment',v)}/>
      <Select label="Етап роботи" options={{open:states.open,working:states.working,retest:states.retest}} value={d.workflow} onChange={v=>update('workflow',v)}/>
      {Object.entries(fields).map(([k,v])=><label key={k}>{v}<textarea value={d[k]} maxLength={['title','route'].includes(k)?160:3000}
        required={['title','route','expected'].includes(k)} readOnly={row?.type==='auto' && ['title','route','expected','keyword'].includes(k)}
        onChange={e=>update(k,e.target.value)}/></label>)}</div>
      <button className="btn" disabled={row && !dirty}>Зберегти задачу</button>
    </form>
    {row && <>{row.id.startsWith('benchmark') && <p><a href="https://accordniche.pp.ua/catalog?q=Creed%20Aventus" target="_blank" rel="noreferrer">Пошук ACCORD NICHE</a>
      {' · '}{/^https:\/\//i.test(row.details.competitor) && <a href={row.details.competitor} target="_blank" rel="noreferrer">Картка конкурента</a>}</p>}<h3>Остання перевірка</h3><p>{states[row.status]} · {outcomes[row.result]} · {time(row.checked)}</p>
      <Comparison value={row.comparison}/>{row.actual && <p>Фактичний результат · {row.actual}</p>}{row.log && <pre>{row.log}</pre>}
      <form onSubmit={run}>
        {row.type==='manual' && <><label>Результат нового тесту<select required value={result} onChange={e=>setResult(e.target.value)}>
          <option value="">Оберіть результат</option>{Object.entries(outcomes).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
          {row.id.startsWith('benchmark') && <><p>Відкрийте обидві картки за однаковим запитом. Запишіть URL, ціну за 5 мл, наявність, доставку й дату для кожної пропозиції.</p><div className="audit-grid">
          {Object.entries({store:'ACCORD NICHE',rival:'Конкурентна сторінка'}).map(([k,title])=><label key={k}>{title}
            <textarea required maxLength={1500} value={comparison[k]} onChange={e=>setComparison({...comparison,[k]:e.target.value})}/></label>)}</div></>}
          <label>Фактичний результат<textarea required maxLength={3000} value={actual} onChange={e=>setActual(e.target.value)}/></label>
          <label>Лог або доказ цього запуску<textarea required maxLength={3000} value={log} onChange={e=>setLog(e.target.value)}/></label></>}
        <button className="btn" disabled={dirty}>{row.type==='auto'?'Запустити перевірку':'Зберегти результат тесту'}</button>
      </form><button className="btn ghost" onClick={()=>loadHistory()}>Історія змін</button>
      {history?.length===0 && <p>Історія порожня.</p>}{history?.map(h=><details key={h.row.version}><summary>{time(h.date)} · {h.actor} · {({edit:'Редагування',test:'Тест',create:'Створення'})[h.action]} · {states[h.row.status]}</summary>
        <dl>{Object.entries({...fields,module:'Модуль',priority:'Пріоритет',assessment:'Оцінка',workflow:'Етап'}).map(([k,label])=><div key={k}><dt>{label}</dt><dd>{({module:modules,assessment:assessments,workflow:states})[k]?.[h.row.details[k]] || h.row.details[k] || '—'}</dd></div>)}</dl>
        <Comparison value={h.row.comparison}/><p>{h.row.build}</p><p>{outcomes[h.row.result]} · {h.row.actual}</p><pre>{h.row.log}</pre></details>)}
      {history?.at(-1)?.row.version>1 && <button className="btn" onClick={()=>loadHistory(true)}>Попередні зміни</button>}</>}
    </fieldset></section>
}

function matches(view,r,blockers) {
  if(view==='release') return true
  if(view==='blockers') return blockers.includes(r.id)
  if(view==='manual') return r.type==='manual' && blockers.includes(r.id)
  if(view==='fixed') return r.status==='fixed'
  const extra={dashboard:['blog','api','database','redis'],domains:['nginx','certbot'],miniapp:['bot']}
  return view===r.details.module || extra[view]?.includes(r.details.module)
}

function Workspace({env,view}) {
  const [data,setData]=useState(null)
  const [error,setError]=useState('')
  const [selected,select]=useState(null)
  const [filters,setFilters]=useState({})
  useEffect(()=>{
    let live=true
    api.storeAudit.list(env).then(value=>{if(live)setData(value)}).catch(e=>{if(live)setError(e.message)})
    return ()=>{live=false}
  },[env])
  async function refresh(id) { setData(await api.storeAudit.list(env)); select(id) }
  if(error) return <p role="alert">{error} <button className="btn" onClick={()=>refresh(null).then(()=>setError('')).catch(e=>setError(e.message))}>Повторити</button></p>
  if(!data) return <p role="status">Завантажуємо перевірки…</p>
  const row=data.items.find(r=>r.id===selected)
  const options={module:modules,status:states,priority,type:types,assessment:assessments}
  const labels={module:'Модуль',status:'Статус',priority:'Пріоритет',type:'Тип перевірки',assessment:'Стан доказів'}
  const items=data.items.filter(r=>matches(view,r,data.blockers) && Object.entries(filters).every(([k,v])=>!v ||
    ({...r.details,...r,assessment:rank(r)})[k]===v))
  return <><header><h2>{views[view]}</h2><button className="btn" onClick={()=>select('new')}>Додати задачу</button></header>
    {view==='release' && <div className="card"><strong>{data.ready?'Готовність підтверджено':'Готовність не підтверджено'}</strong>
      <p>Повторно підтверджено {data.items.length-data.blockers.length} із {data.items.length}. Для готовності потрібні докази поточної збірки API за останні 7 днів для кожної перевірки середовища.</p>
      <Link to="/store-audit/blockers">Блокери релізу ({data.blockers.length})</Link></div>}
    {selected && <Editor key={selected+':'+(row?.version||0)} env={env} row={row} close={()=>select(null)} refresh={refresh}/>}
    <div className="audit-grid">{Object.entries(options).map(([k,opts])=><Select key={k} label={labels[k]} options={opts} all
      value={filters[k]||''} onChange={v=>setFilters(prev=>({...prev,[k]:v}))}/>)}</div>
    <p>Знайдено перевірок · {items.length}</p>
    {items.map(r=><article className="card audit-row" key={r.id}><div><strong>{r.details.title}</strong>
      <p>{modules[r.details.module]} · {r.details.priority} · {types[r.type]} · {time(r.checked)}</p>
      <span>{states[r.status]} · {assessments[rank(r)]}</span></div>
      <button className="btn ghost" onClick={()=>{select(r.id); window.scrollTo(0,0)}}>Відкрити</button></article>)}
    {items.length===0 && <p>Записів із такими умовами немає.</p>}</>
}

export default function StoreAudit() {
  const {view='release'}=useParams()
  const [env,setEnv]=useState('production')
  if(!Object.hasOwn(views,view)) return <Navigate replace to="/store-audit/release"/>
  return <div className="store-audit"><header><h1>Контроль магазину</h1>
    <Select label="Середовище" value={env} options={envs} onChange={setEnv}/></header>
    <nav aria-label="Подання аудиту">{Object.entries(views).map(([id,title])=><NavLink className={'btn ghost'+(view===id?' selected':'')} key={id} to={'/store-audit/'+id}>{title}</NavLink>)}</nav>
    <Workspace key={env+':'+view} env={env} view={view}/></div>
}
