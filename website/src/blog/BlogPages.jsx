import {useEffect,useState} from 'react'
import {useStoreRequest} from '../useStoreRequest'
import BlogContent from './BlogContent'
import {StateBlock,errorTitle} from '../ui/states'

const date=value=>value?new Intl.DateTimeFormat('uk-UA',{dateStyle:'medium'}).format(new Date(value)):''
const key=()=>crypto.randomUUID()
const signedIn=account=>Boolean(account?.signed_in || account?.phone_verified || account?.telegram_linked)

function State({request,children}) {
  if(!request.data && request.loading)return <StateBlock kind="loading" className="blog-state">Завантажуємо блог…</StateBlock>
  if(request.error)return <StateBlock kind="error" className="blog-state" title={errorTitle(request,'Публікацію не знайдено')}
    action={<button className="btn outline" onClick={request.retry}>Спробувати ще раз</button>}><p>{request.error.replace('Товар більше недоступний.','Публікацію не знайдено або її ще не опубліковано.')}</p></StateBlock>
  return children
}

// W-25: a comment's state in words and colour, so nobody wonders whether it is
// already public or only sent.
const COMMENT_STATUS={pending:['warn','На модерації · бачите лише ви'],approved:['ok','Опубліковано'],rejected:['off','Не схвалено редакцією']}

export function BlogList({route,go}) {
  const query=new URLSearchParams(route.split('?')[1] || '')
  const [search,setSearch]=useState(query.get('q') || '')
  const page=Math.max(1,parseInt(query.get('page') || '1',10) || 1)
  const request=useStoreRequest('/api/public/blog?q='+encodeURIComponent(query.get('q') || '')+'&limit=12&offset='+((page-1)*12))
  useEffect(()=>setSearch(query.get('q') || ''),[route])
  useEffect(()=>{const old=document.title;document.title='Блог — ACCORD NICHE';return()=>{document.title=old}},[])
  function navigate(nextPage=1,term=query.get('q') || '') {
    const next=new URLSearchParams()
    if(term.trim())next.set('q',term.trim())
    if(nextPage>1)next.set('page',String(nextPage))
    go('/blog'+(next.size?'?'+next:''))
  }
  const data=request.data
  return <main className="shell blog-page"><header className="blog-heading"><p className="eyebrow">ЖУРНАЛ ACCORD NICHE</p><h1>Блог</h1><p>Про аромати, знайомство з парфумерією та життя магазину.</p></header>
    <form className="blog-search" role="search" onSubmit={event=>{event.preventDefault();navigate(1,search)}}><input aria-label="Пошук у блозі" placeholder="Знайти публікацію…" value={search} maxLength={120} onChange={event=>setSearch(event.target.value)}/><button className="btn outline" type="submit">Знайти</button></form>
    <State request={request}>{data?.items.length===0?<div className="blog-state"><h2>{query.get('q')?'Публікацій не знайдено':'Скоро тут з’являться публікації'}</h2><p>{query.get('q')?'Спробуйте інший пошуковий запит.':'Нові матеріали редакції будуть доступні на цій сторінці.'}</p></div>:<div className="blog-grid">{data?.items.map(post=><article className="blog-card" key={post.id}><button className="blog-card-link" onClick={()=>go('/blog/'+encodeURIComponent(post.slug))}>{post.cover_url && <img src={post.cover_url} alt="" loading="lazy" referrerPolicy="no-referrer"/>}<div className="blog-card-content"><p className="blog-meta">{date(post.published_at)} · {post.reading_minutes} хв читання</p><h2>{post.title}</h2><p>{post.excerpt}</p><span>Читати →</span></div></button><p className="blog-card-footer">{post.author_name} · Коментарів: {post.comment_count}</p></article>)}</div>}</State>
    {data?.total>12 && <nav className="catalog-pagination" aria-label="Сторінки блогу"><button className="btn outline" disabled={page===1} onClick={()=>navigate(page-1)}>← Назад</button><span>{page} / {Math.ceil(data.total/12)}</span><button className="btn outline" disabled={page*12>=data.total} onClick={()=>navigate(page+1)}>Далі →</button></nav>}
  </main>
}

function Thread({comment,slug,canReply,onReply}) {
  const [open,setOpen]=useState(false)
  const [page,setPage]=useState(1)
  const request=useStoreRequest(open?'/api/public/blog/'+encodeURIComponent(slug)+'/comments?parent_id='+comment.id+'&offset='+((page-1)*10):null)
  return <article className="blog-comment"><header><strong>{comment.author_name}</strong>{comment.is_staff && <span className="staff-label">Редакція</span>}<time>{date(comment.created_at)}</time></header><p>{comment.body}</p>
    <div className="comment-actions">{canReply && <button onClick={()=>onReply(comment)}>Відповісти</button>}{comment.reply_count>0 && <button aria-expanded={open} onClick={()=>setOpen(value=>!value)}>Відповіді ({comment.reply_count}) {open?'↑':'↓'}</button>}</div>
    {open && <div className="blog-replies"><State request={request}>{request.data?.items.map(reply=><article className="blog-comment" key={reply.id}><header><strong>{reply.author_name}</strong>{reply.is_staff && <span className="staff-label">Редакція</span>}<time>{date(reply.created_at)}</time></header><p>{reply.body}</p></article>)}</State>{request.data?.total>10 && <nav className="comment-actions"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>←</button><span>{page}</span><button disabled={page*10>=request.data.total} onClick={()=>setPage(value=>value+1)}>→</button></nav>}</div>}
  </article>
}

function Comments({post,shop,go,onChanged}) {
  const [page,setPage]=useState(1)
  const [body,setBody]=useState('')
  const [clientKey,setClientKey]=useState(key)
  const [replyTo,setReplyTo]=useState(null)
  const [editing,setEditing]=useState(null)
  const [busy,setBusy]=useState(false)
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const authenticated=signedIn(shop.account)
  const visible=useStoreRequest('/api/public/blog/'+encodeURIComponent(post.slug)+'/comments?offset='+((page-1)*10))
  const mine=useStoreRequest(authenticated?'/api/web/blog/posts/'+post.id+'/mine':null)
  useEffect(()=>{
    if(!body.trim())return
    const guard=event=>{event.preventDefault();event.returnValue=''}
    window.addEventListener('beforeunload',guard)
    return()=>window.removeEventListener('beforeunload',guard)
  },[body])
  async function submit(event) {
    event.preventDefault()
    if(busy)return
    setBusy(true);setError('');setMessage('')
    try {
      if(editing)await shop.request('/blog/comments/'+editing.id,'PUT',{body,version:editing.version})
      else await shop.request('/blog/posts/'+post.id+'/comments','POST',{body,parent_id:replyTo?.id || null,client_key:clientKey})
      setBody('');setEditing(null);setReplyTo(null);setClientKey(key())
      setMessage(editing?'Зміни надіслано на модерацію. До схвалення коментар має статус «На модерації» у блоці «Ваші коментарі».':'Коментар надіслано на модерацію. Його видно у блоці «Ваші коментарі» зі статусом «На модерації»; після схвалення його побачать усі.')
      mine.retry();visible.retry();onChanged()
    } catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  async function remove(comment) {
    if(busy || !window.confirm('Видалити свій коментар?'))return
    setBusy(true);setError('')
    try{await shop.request('/blog/comments/'+comment.id,'DELETE',{version:comment.version});mine.retry();visible.retry();onChanged();setMessage('Коментар видалено.')}
    catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  function cancel(){setEditing(null);setReplyTo(null);setBody('');setClientKey(key())}
  function reply(comment){setEditing(null);setReplyTo(comment);setClientKey(key());document.getElementById('blog-comment-body')?.focus()}
  return <section className="blog-comments" aria-labelledby="comments-title"><div className="section-row"><h2 id="comments-title">Обговорення</h2><span>Коментарів: {post.comment_count}</span></div>
    <State request={visible}>{visible.data?.items.length===0 && <p className="blog-state">Схвалених коментарів поки немає.</p>}{visible.data?.items.map(comment=><Thread key={comment.id+':'+comment.reply_count} comment={comment} slug={post.slug} canReply={authenticated && post.comments_enabled} onReply={reply}/>)}</State>
    {visible.data?.total>10 && <nav className="comment-actions" aria-label="Сторінки коментарів"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>← Назад</button><span>{page}</span><button disabled={page*10>=visible.data.total} onClick={()=>setPage(value=>value+1)}>Далі →</button></nav>}
    {authenticated && <section className="own-comments"><h3>Ваші коментарі</h3><State request={mine}>{mine.data?.length===0 && <p>Ви ще не коментували цю статтю.</p>}{mine.data?.map(comment=><div className="own-comment" key={comment.id}><span className={'status-chip '+(COMMENT_STATUS[comment.status]?.[0]||'')}>{COMMENT_STATUS[comment.status]?.[1]||comment.status}</span><p>{comment.body}</p><div className="comment-actions">{post.comments_enabled && <button disabled={busy} onClick={()=>{setEditing(comment);setReplyTo(null);setBody(comment.body);document.getElementById('blog-comment-body')?.focus()}}>Редагувати</button>}<button disabled={busy} onClick={()=>remove(comment)}>Видалити</button></div></div>)}</State></section>}
    {error && <p className="shop-error" role="alert">{error}</p>}{message && <p className="shop-success" role="status">{message}</p>}
    {!post.comments_enabled?<p className="blog-state">Нові коментарі до цієї публікації закрито.</p>:authenticated?<form className="comment-form" onSubmit={submit}><h3>{editing?'Редагувати свій коментар':'Залишити коментар'}</h3>{replyTo && !editing && <p className="reply-target" role="status">Відповідаєте: <strong>{replyTo.author_name}</strong> <button type="button" className="text-muted-button" disabled={busy} onClick={cancel}>Скасувати відповідь</button></p>}<label htmlFor="blog-comment-body">Ваш коментар</label><textarea id="blog-comment-body" value={body} minLength={2} maxLength={2000} required disabled={busy} onChange={event=>{setBody(event.target.value);if(!editing)setClientKey(key())}} rows={5}/><p className="blog-meta">{body.length} / 2000</p><p className="comment-rules">Коментарі публікуються після перевірки редакцією. Відредагований коментар перевіряється знову. Не залишайте в тексті телефон, адресу чи інші особисті дані.</p><div className="comment-actions"><button className="btn primary" type="submit" disabled={busy || body.trim().length<2}>{busy?'Надсилаємо…':'Надіслати на модерацію'}</button>{editing && <button type="button" disabled={busy} onClick={cancel}>Скасувати редагування</button>}</div></form>:<div className="blog-state"><p>Щоб залишити коментар, увійдіть в особистий кабінет.</p><button className="btn primary" onClick={()=>go('/profile?returnTo='+encodeURIComponent('/blog/'+post.slug))}>Увійти та коментувати</button></div>}
  </section>
}

export function BlogArticle({slug,shop,go}) {
  const request=useStoreRequest('/api/public/blog/'+encodeURIComponent(slug))
  const post=request.data
  useEffect(()=>{
    if(!post)return
    if(post.slug!==slug){go('/blog/'+encodeURIComponent(post.slug),{replace:true});return}
    const previous=document.title
    document.title=post.title+' — ACCORD NICHE'
    const meta=document.querySelector('meta[name="description"]')
    const description=meta?.getAttribute('content')
    if(meta)meta.setAttribute('content',post.excerpt || post.title)
    return()=>{document.title=previous;if(meta && description!=null)meta.setAttribute('content',description)}
  },[post?.id,post?.slug,slug])
  return <main className="shell blog-page blog-article"><button className="back-link" onClick={()=>go('/blog')}>← Усі публікації</button><State request={request}>{post && <><header className="blog-heading"><p className="blog-meta">{date(post.published_at)} · {post.reading_minutes} хв читання</p><h1>{post.title}</h1><p>{post.excerpt}</p><span className="blog-byline">{post.author_name}</span></header>{post.cover_url && <img className="blog-cover" src={post.cover_url} alt="" referrerPolicy="no-referrer"/>}<BlogContent body={post.body}/><Comments key={post.id+':'+(shop.account.account_key || 'guest')} post={post} shop={shop} go={go} onChanged={request.retry}/></>}</State></main>
}
