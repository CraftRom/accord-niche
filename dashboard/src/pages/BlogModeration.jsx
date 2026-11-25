import {useEffect,useState} from 'react'
import {api} from '../api'
import {Empty,ErrorBar,Field,Loading,useToast} from '../components/ui'

const date=value=>value?new Intl.DateTimeFormat('uk-UA',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)):'—'
const STATUS={pending:'На модерації',approved:'Схвалено',rejected:'Відхилено',deleted:'Видалено автором'}
const FLAGS={stop_word:'Стоп-слово',link:'Посилання',contact:'Контакти'}
const DURATIONS=[['1','1 день'],['7','7 днів'],['30','30 днів'],['365','1 рік'],['','Назавжди']]

function BanForm({comment,onDone,onCancel}) {
  const [reason,setReason]=useState('')
  const [days,setDays]=useState('30')
  const [comments,setComments]=useState('hide')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  async function submit(event) {
    event.preventDefault()
    if(busy)return
    if(comments==='delete' && !window.confirm('Видалити всі коментарі цього автора назавжди?'))return
    setBusy(true);setError('')
    try{await api.blog.ban({user_id:comment.author_user_id,reason,days:days?Number(days):null,comments});onDone()}
    catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  return <form className="blog-ban-form" onSubmit={submit}><h3>Заблокувати {comment.author_name}</h3><ErrorBar error={error}/>
    <fieldset disabled={busy}><Field label="Причина (бачить лише редакція)"><input aria-label="Причина блокування" className="input" maxLength={500} value={reason} onChange={event=>setReason(event.target.value)} placeholder="Спам, образи, реклама…"/></Field>
    <div className="blog-ban-grid"><Field label="Строк"><select aria-label="Строк блокування" className="input" value={days} onChange={event=>setDays(event.target.value)}>{DURATIONS.map(([value,label])=><option key={label} value={value}>{label}</option>)}</select></Field>
    <Field label="Наявні коментарі"><select aria-label="Наявні коментарі автора" className="input" value={comments} onChange={event=>setComments(event.target.value)}><option value="hide">Приховати (відхилити)</option><option value="none">Залишити як є</option><option value="delete">Видалити назавжди</option></select></Field></div>
    <p className="muted">Блокування діє на всі способи входу покупця (Google, телефон, Telegram). Він бачить пояснення, але не може писати чи редагувати коментарі.</p>
    <div className="actions"><button className="btn danger" type="submit">Заблокувати</button><button className="btn" type="button" onClick={onCancel}>Скасувати</button></div></fieldset></form>
}

export function CommentQueue({onCountsChange}) {
  const notify=useToast()
  const [status,setStatus]=useState('pending')
  const [q,setQ]=useState('')
  const [search,setSearch]=useState('')
  const [flagged,setFlagged]=useState(false)
  const [author,setAuthor]=useState(null)
  const [page,setPage]=useState(0)
  const [data,setData]=useState(null)
  const [selected,setSelected]=useState(()=>new Set())
  const [notes,setNotes]=useState({})
  const [reply,setReply]=useState(null)
  const [replyBody,setReplyBody]=useState('')
  const [replyKey,setReplyKey]=useState(()=>crypto.randomUUID())
  const [banning,setBanning]=useState(null)
  const [busy,setBusy]=useState(false)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [revision,setRevision]=useState(0)
  const [loadedKey,setLoadedKey]=useState(null)
  const refresh=()=>setRevision(value=>value+1)
  // Results of another filter are never actionable: they disappear while the
  // new filter loads and stay hidden if it fails. A failed refresh of the same
  // filter keeps the loaded queue and shows the error.
  const queryKey=JSON.stringify([status,search,flagged,author?.id,page])
  useEffect(()=>{const timer=setTimeout(()=>{setSearch(q);setPage(0)},300);return()=>clearTimeout(timer)},[q])
  useEffect(()=>{
    let active=true
    setLoading(true);setError('')
    api.blog.comments({status:status || 'all',q:search,flagged:flagged || undefined,author_user_id:author?.id,limit:20,offset:page*20})
      .then(result=>{if(active){setData(result);setLoadedKey(queryKey);setSelected(new Set());if(result.counts)onCountsChange?.(result.counts)}})
      .catch(error=>{if(active)setError(error.message)})
      .finally(()=>{if(active)setLoading(false)})
    return()=>{active=false}
  },[status,search,flagged,author?.id,page,revision])
  useEffect(()=>{
    if(reply || busy || banning)return
    const timer=setInterval(()=>{if(!document.hidden)refresh()},30000)
    return()=>clearInterval(timer)
  },[reply,busy,banning])
  async function run(action,message) {
    setBusy(true);setError('')
    try{await action();refresh();notify(message)}
    catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  const moderate=(comment,next)=>run(()=>api.blog.moderate(comment.id,{status:next,version:comment.version,note:notes[comment.id] ?? comment.moderation_note ?? ''}),next==='approved'?'Коментар схвалено':'Коментар приховано')
  const remove=comment=>window.confirm('Видалити коментар назавжди'+(comment.reply_count||!comment.parent_id?' разом із відповідями':'')+'?') && run(()=>api.blog.removeComment(comment.id),'Коментар видалено')
  const bulk=action=>{
    const ids=[...selected]
    if(!ids.length)return
    if(action==='delete' && !window.confirm('Видалити назавжди вибрані коментарі ('+ids.length+') разом із відповідями?'))return
    run(()=>api.blog.bulk({ids,action}),{approve:'Схвалено',reject:'Приховано',delete:'Видалено'}[action]+': '+ids.length)
  }
  async function sendReply(event) {
    event.preventDefault()
    if(busy)return
    await run(()=>api.blog.reply(reply.post_id,{parent_id:reply.id,body:replyBody,client_key:replyKey}),'Відповідь редакції опубліковано')
    setReply(null);setReplyBody('');setReplyKey(crypto.randomUUID())
  }
  const current=loadedKey===queryKey?data:null
  const items=current?.items || []
  const all=items.length>0 && items.every(comment=>selected.has(comment.id))
  const toggle=id=>setSelected(old=>{const next=new Set(old);next.has(id)?next.delete(id):next.add(id);return next})
  const counts=current?.counts || data?.counts || {}
  return <>
    <div className="blog-admin-filters"><select className="input" aria-label="Стан коментарів" value={status} onChange={event=>{setStatus(event.target.value);setPage(0)}}>
      {['pending','approved','rejected','deleted'].map(key=><option key={key} value={key}>{STATUS[key]} ({counts[key] ?? 0})</option>)}<option value="">Усі коментарі</option></select>
      <input className="input" aria-label="Пошук у коментарях" placeholder="Текст або ім’я автора…" value={q} onChange={event=>setQ(event.target.value)}/>
      <label className="blog-check"><input type="checkbox" checked={flagged} onChange={event=>{setFlagged(event.target.checked);setPage(0)}}/>Лише з позначками автомодерації</label>
      <button className="btn" disabled={loading || busy} onClick={refresh}>Оновити</button></div>
    {author && <p className="blog-author-filter">Коментарі автора <strong>{author.name}</strong> <button className="btn small" onClick={()=>{setAuthor(null);setPage(0)}}>Показати всіх</button></p>}
    <ErrorBar error={error}/>
    {items.length>0 && <div className="blog-bulk-bar"><label className="blog-check"><input type="checkbox" aria-label="Вибрати всі на сторінці" checked={all} onChange={()=>setSelected(all?new Set():new Set(items.map(comment=>comment.id)))}/>Вибрано: {selected.size}</label>
      <button className="btn primary" disabled={busy || !selected.size} onClick={()=>bulk('approve')}>Схвалити</button><button className="btn" disabled={busy || !selected.size} onClick={()=>bulk('reject')}>Відхилити</button><button className="btn danger" disabled={busy || !selected.size} onClick={()=>bulk('delete')}>Видалити</button></div>}
    {!current?(loading?<Loading/>:null):items.length===0?<Empty title="Черга порожня">Коментарів за цим фільтром немає.</Empty>:items.map(comment=><article className={'card blog-moderation-item'+(selected.has(comment.id)?' selected':'')} key={comment.id}>
      <div className="blog-moderation-head"><label className="blog-check"><input type="checkbox" aria-label={'Вибрати коментар '+comment.id} checked={selected.has(comment.id)} onChange={()=>toggle(comment.id)}/></label>
        <div><p className="muted">{comment.post_title} · {date(comment.created_at)}{comment.parent_id?' · відповідь':''}</p>
        <h3>{comment.author_name} {comment.is_staff?'· Редакція':''}{comment.author_banned && <span className="blog-flag danger">Заблокований</span>}</h3>
        {!comment.is_staff && comment.author_user_id && <p className="muted">Історія автора: схвалено {comment.author_approved} · відхилено {comment.author_rejected}</p>}</div></div>
      <p className="blog-comment-text">{comment.body || 'Текст видалено автором'}</p>
      <div className="blog-flags"><span className="blog-admin-status">{STATUS[comment.status]}</span>{(comment.flags || '').split(',').filter(Boolean).map(flag=><span className="blog-flag" key={flag}>{FLAGS[flag] || flag}</span>)}{comment.moderated_by==='auto' && <span className="blog-flag">Автомодерація</span>}</div>
      {comment.status!=='deleted' && <Field label="Внутрішня примітка модератора"><input aria-label="Внутрішня примітка модератора" className="input" maxLength={500} value={notes[comment.id] ?? comment.moderation_note} onChange={event=>setNotes(old=>({...old,[comment.id]:event.target.value}))}/></Field>}
      <div className="actions">{comment.status!=='deleted' && <><button className="btn primary" disabled={busy || comment.status==='approved'} onClick={()=>moderate(comment,'approved')}>Схвалити</button><button className="btn" disabled={busy || comment.status==='rejected'} onClick={()=>moderate(comment,'rejected')}>Відхилити / приховати</button><button className="btn" disabled={busy || comment.status!=='approved' || comment.parent_id!==null} onClick={()=>{setReply(comment);setReplyBody('');setReplyKey(crypto.randomUUID())}}>Відповісти</button></>}
        <button className="btn danger" disabled={busy} onClick={()=>remove(comment)}>Видалити</button>
        {!comment.is_staff && comment.author_user_id && <><button className="btn" disabled={busy} onClick={()=>{setAuthor({id:comment.author_user_id,name:comment.author_name});setPage(0)}}>Усі коментарі автора</button>{!comment.author_banned && <button className="btn" disabled={busy} onClick={()=>setBanning(comment)}>Заблокувати автора</button>}</>}
        {comment.post_slug && comment.status==='approved' && <a className="btn" href={'https://accordniche.pp.ua/blog/'+encodeURIComponent(comment.post_slug)} target="_blank" rel="noopener noreferrer">На сайті</a>}</div>
      {banning?.id===comment.id && <BanForm comment={comment} onCancel={()=>setBanning(null)} onDone={()=>{setBanning(null);refresh();notify('Автора заблоковано')}}/>}
    </article>)}
    {reply && <form className="card" onSubmit={sendReply}><h2>Відповідь для {reply.author_name}</h2><Field label="Відповідь редакції"><textarea aria-label="Відповідь редакції" className="input" required minLength={2} maxLength={2000} rows={4} value={replyBody} onChange={event=>{setReplyBody(event.target.value);setReplyKey(crypto.randomUUID())}}/></Field><p className="muted">Відповідь адміністратора буде опублікована одразу.</p><div className="actions"><button className="btn primary" type="submit" disabled={busy}>Опублікувати відповідь</button><button className="btn" type="button" disabled={busy} onClick={()=>setReply(null)}>Скасувати</button></div></form>}
    {current?.total>20 && <nav className="blog-admin-pagination" aria-label="Сторінки"><button className="btn" disabled={page===0 || loading} onClick={()=>setPage(value=>value-1)}>← Назад</button><span>{page+1} / {Math.ceil(current.total/20)}</span><button className="btn" disabled={(page+1)*20>=current.total || loading} onClick={()=>setPage(value=>value+1)}>Далі →</button></nav>}
  </>
}

export function BanList() {
  const notify=useToast()
  const [bans,setBans]=useState(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const load=()=>api.blog.bans().then(setBans).catch(error=>setError(error.message))
  useEffect(()=>{load()},[])
  async function unban(ban) {
    if(!window.confirm('Зняти блокування з '+(ban.author_name || 'автора')+'?'))return
    setBusy(true);setError('')
    try{await api.blog.unban(ban.user_id);await load();notify('Блокування знято')}
    catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  const active=ban=>!ban.expires_at || new Date(ban.expires_at)>new Date()
  return <><ErrorBar error={error}/>{!bans?<Loading/>:bans.length===0?<Empty title="Заблокованих авторів немає">Заблокувати автора можна з черги коментарів.</Empty>:<div className="blog-admin-posts">{bans.map(ban=><article className="card" key={ban.user_id}><div><span className="blog-admin-status">{active(ban)?'Діє':'Строк минув'}</span><h2>{ban.author_name || 'Покупець #'+ban.user_id}</h2><p>{ban.reason || 'Причину не вказано'}</p><p className="muted">З {date(ban.created_at)} · {ban.expires_at?'до '+date(ban.expires_at):'назавжди'} · {ban.banned_by} · коментарів: {ban.comment_count}</p></div><div className="actions"><button className="btn" disabled={busy} onClick={()=>unban(ban)}>Розблокувати</button></div></article>)}</div>}</>
}

export function ModerationRules() {
  const notify=useToast()
  const [form,setForm]=useState(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{api.blog.moderationSettings().then(setForm).catch(error=>setError(error.message))},[])
  const set=(key,value)=>setForm(old=>({...old,[key]:value}))
  async function save(event) {
    event.preventDefault()
    setBusy(true);setError('')
    try{const {mode,trusted_after,stop_words,stop_word_action,hold_links}=form;setForm(await api.blog.saveModerationSettings({mode,trusted_after:Number(trusted_after),stop_words,stop_word_action,hold_links}));notify('Правила модерації збережено')}
    catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  if(!form)return <><ErrorBar error={error}/>{!error && <Loading/>}</>
  return <form className="card blog-rules" onSubmit={save}><ErrorBar error={error}/><fieldset disabled={busy}>
    <Field label="Режим публікації"><select aria-label="Режим публікації" className="input" value={form.mode} onChange={event=>set('mode',event.target.value)}><option value="manual">Кожен коментар перевіряє редакція</option><option value="trusted">Довірені автори публікуються одразу</option></select></Field>
    {form.mode==='trusted' && <Field label="Довірений автор — після скількох схвалених коментарів" hint="І жодного відхиленого. Коментарі з посиланнями, контактами чи стоп-словами все одно чекають перевірки."><input aria-label="Поріг довіри" className="input" type="number" min="1" max="100" value={form.trusted_after} onChange={event=>set('trusted_after',event.target.value)}/></Field>}
    <Field label="Стоп-слова" hint="Через кому або з нового рядка. Шукаються цілі слова без урахування регістру."><textarea aria-label="Стоп-слова" className="input" rows={5} maxLength={5000} value={form.stop_words} onChange={event=>set('stop_words',event.target.value)}/></Field>
    <Field label="Коментар зі стоп-словом"><select aria-label="Дія для стоп-слова" className="input" value={form.stop_word_action} onChange={event=>set('stop_word_action',event.target.value)}><option value="hold">Лишити в черзі з позначкою</option><option value="reject">Відхилити одразу</option></select></Field>
    <label className="blog-check"><input type="checkbox" checked={form.hold_links} onChange={event=>set('hold_links',event.target.checked)}/>Коментарі з посиланнями завжди чекають перевірки</label>
    <p className="muted">Телефони та e-mail у тексті завжди позначаються й чекають модератора: це захищає покупців від публікації особистих даних.{form.updated_by?' Востаннє змінено: '+form.updated_by+', '+date(form.updated_at)+'.':''}</p>
    <button className="btn primary" type="submit">{busy?'Зберігаємо…':'Зберегти правила'}</button></fieldset></form>
}
