import {useCallback,useEffect,useRef,useState} from 'react'
import {api} from '../api'
import {Empty,ErrorBar,Field,Loading,useToast} from '../components/ui'
import ImageField from '../components/ImageField'
import BlogContent from '../components/BlogContent'
import {Counter,SEO_LIMITS,SeoSnippet} from '../components/SeoSnippet'
import {BanList,CommentQueue,ModerationRules} from './BlogModeration'
import './blog.css'

const SEO_BLANK={seo_title:'',seo_description:'',focus_keyword:'',cover_alt:'',noindex:false}
const blank=()=>({title:'',slug:'',excerpt:'',body:'',cover_url:'',author_name:'Редакція ACCORD NICHE',status:'draft',published_at:'',comments_enabled:true,...SEO_BLANK})
const date=value=>value?new Intl.DateTimeFormat('uk-UA',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)):'—'
function localDate(value) {
  if(!value)return ''
  const parsed=new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)?value:value+'Z')
  return new Date(parsed.getTime()-parsed.getTimezoneOffset()*60000).toISOString().slice(0,16)
}
function formOf(post) {
  return {title:post.title,slug:post.slug,excerpt:post.excerpt,body:post.body,cover_url:post.cover_url,author_name:post.author_name,
    status:post.status,published_at:localDate(post.published_at),comments_enabled:post.comments_enabled,version:post.version,
    seo_title:post.seo_title||'',seo_description:post.seo_description||'',focus_keyword:post.focus_keyword||'',cover_alt:post.cover_alt||'',noindex:Boolean(post.noindex)}
}
function state(post) {
  if(post.status==='published')return post.published_at && new Date(post.published_at)>new Date()?'Заплановано':'Опубліковано'
  return post.status==='archived'?'Архів':'Чернетка'
}

const plain=body=>(body||'').replace(/!\[[^\]]*\]\([^)]*\)/g,' ').replace(/\[([^\]]*)\]\([^)]*\)/g,'$1').replace(/[#*_>`]/g,' ').replace(/\s+/g,' ').trim()
// Editorial SEO checklist: the same rules a search specialist would check by hand.
export function seoChecks(form) {
  const title=(form.seo_title || form.title || '').trim()
  const description=(form.seo_description || form.excerpt || plain(form.body).slice(0,160)).trim()
  const words=plain(form.body).split(' ').filter(Boolean).length
  const keyword=form.focus_keyword.trim().toLocaleLowerCase('uk')
  const has=text=>keyword && (text||'').toLocaleLowerCase('uk').includes(keyword)
  const firstParagraph=plain((form.body||'').split(/\n\s*\n/).find(part=>part.trim() && !part.trim().startsWith('#')) || '')
  const images=[...(form.body||'').matchAll(/!\[([^\]]*)\]\(/g)].map(match=>match[1].trim())
  return [
    ['Заголовок для Google 30–60 символів',title.length>=30 && title.length<=60],
    ['Опис для Google 70–160 символів',description.length>=70 && description.length<=160],
    ['Ключова фраза задана',Boolean(keyword)],
    ['Ключова фраза в заголовку',has(title)],
    ['Ключова фраза в описі',has(description)],
    ['Ключова фраза в першому абзаці',has(firstParagraph)],
    ['Текст від 300 слів (зараз '+words+')',words>=300],
    ['Є підзаголовки (## …)',/^##\s+\S/m.test(form.body||'')],
    ['Є посилання на каталог або аромат',/\]\((?:https:\/\/accordniche\.pp\.ua)?\/(?:catalog|aroma|brands|sets)/.test(form.body||'')],
    ['Обкладинка з alt-текстом',Boolean(form.cover_url && form.cover_alt.trim())],
    ['Усі зображення в тексті мають опис',images.every(alt=>alt && alt!=='Опис зображення')],
    ['Коротка адреса (до 75 символів)',(form.slug || '').length<=75],
  ]
}

function SeoPanel({form,set}) {
  const checks=seoChecks(form)
  const done=checks.filter(([,ok])=>ok).length
  const title=form.seo_title.trim() || (form.title ? form.title+' | ACCORD NICHE' : '')
  const description=form.seo_description.trim() || form.excerpt.trim() || plain(form.body).slice(0,160)
  return <section className="blog-seo" aria-label="SEO статті"><h2>SEO</h2>
    <SeoSnippet title={title} description={description} url={'accordniche.pp.ua › blog › '+(form.slug || 'адреса-статті')}/>
    <Field label="SEO-заголовок" hint="Порожнє — заголовок статті + назва магазину."><input aria-label="SEO-заголовок" className="input" maxLength={120} value={form.seo_title} onChange={event=>set('seo_title',event.target.value)}/><Counter value={form.seo_title || title} limits={SEO_LIMITS.title}/></Field>
    <Field label="SEO-опис" hint="Порожнє — короткий опис статті."><textarea aria-label="SEO-опис" className="input" rows={3} maxLength={300} value={form.seo_description} onChange={event=>set('seo_description',event.target.value)}/><Counter value={form.seo_description || description} limits={SEO_LIMITS.description}/></Field>
    <Field label="Ключова фраза" hint="Запит, за яким стаття має знаходитися: «як обрати нішевий аромат»."><input aria-label="Ключова фраза" className="input" maxLength={80} value={form.focus_keyword} onChange={event=>set('focus_keyword',event.target.value)}/></Field>
    <p className="seo-score">Готовність: {done} / {checks.length}</p>
    <ul className="seo-checklist">{checks.map(([label,ok])=><li key={label} className={ok?'':'todo'}>{label}</li>)}</ul>
    <label className="blog-check"><input type="checkbox" checked={form.noindex} onChange={event=>set('noindex',event.target.checked)}/>Не індексувати (noindex): стаття доступна за посиланням, але не в пошуку й sitemap</label>
  </section>
}

function Editor({post,onClose,onSaved}) {
  const [form,setForm]=useState(()=>post?formOf(post):blank())
  const [base,setBase]=useState(()=>JSON.stringify(post?formOf(post):blank()))
  const [busy,setBusy]=useState(false)
  const [uploading,setUploading]=useState(false)
  const [error,setError]=useState('')
  const [conflict,setConflict]=useState(false)
  const [backup,setBackup]=useState('')
  const [preview,setPreview]=useState(false)
  const [imagePicker,setImagePicker]=useState(false)
  const [inlineImage,setInlineImage]=useState('')
  const text=useRef(null)
  const dirty=JSON.stringify(form)!==base
  useEffect(()=>{
    if(!dirty)return
    const guard=event=>{event.preventDefault();event.returnValue=''}
    const navigate=event=>{
      const link=event.target.closest?.('a[href]')
      if(!link || link.target==='_blank' || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)return
      if(!window.confirm('Є незбережені зміни. Залишити редактор?')){event.preventDefault();event.stopImmediatePropagation()}
    }
    window.addEventListener('beforeunload',guard)
    document.addEventListener('click',navigate,true)
    return()=>{window.removeEventListener('beforeunload',guard);document.removeEventListener('click',navigate,true)}
  },[dirty])
  const set=(key,value)=>setForm(old=>({...old,[key]:value}))
  function close(){if(!busy && (!dirty || window.confirm('Є незбережені зміни. Закрити редактор?')))onClose()}
  function insert(before,after='') {
    const start=text.current?.selectionStart ?? form.body.length
    const end=text.current?.selectionEnd ?? start
    set('body',form.body.slice(0,start)+before+form.body.slice(start,end)+after+form.body.slice(end))
    requestAnimationFrame(()=>text.current?.focus())
  }
  async function save(event) {
    event.preventDefault()
    if(busy || uploading)return
    setBusy(true);setError('');setConflict(false)
    try {
      const payload={...form,published_at:form.published_at?new Date(form.published_at).toISOString():null}
      const result=post?await api.blog.update(post.id,payload):await api.blog.create(payload)
      const next=formOf(result)
      setForm(next);setBase(JSON.stringify(next));onSaved(result)
    } catch(error){setError(error.message);setConflict(error.status===409)}
    finally{setBusy(false)}
  }
  async function reload() {
    setBusy(true)
    try {
      const current=await api.blog.post(post.id)
      setBackup(form.body);setForm(formOf(current));setBase(JSON.stringify(formOf(current)));setConflict(false)
      setError('Завантажено поточну версію. Ваш попередній текст збережений нижче для порівняння.')
    } catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  return <section className="blog-admin-editor"><header className="page-head"><div><h1>{post?'Редагувати статтю':'Нова стаття'}</h1><p className="muted">Збереження чернетки не публікує статтю на сайті.</p></div><button className="btn" disabled={busy} onClick={close}>До публікацій</button></header>
    <ErrorBar error={error}/>{conflict && post && <button className="btn" disabled={busy} onClick={reload}>Завантажити поточну версію та зберегти мій текст окремо</button>}
    <form onSubmit={save}><fieldset disabled={busy} className="blog-editor-fields"><div><div className="blog-editor-main"><Field label="Заголовок"><input aria-label="Заголовок" className="input" required minLength={3} maxLength={200} value={form.title} onChange={event=>set('title',event.target.value)}/></Field>
      <Field label="Короткий опис" hint="Буде у списку публікацій та описі сторінки."><textarea aria-label="Короткий опис" className="input" maxLength={500} rows={3} value={form.excerpt} onChange={event=>set('excerpt',event.target.value)}/></Field>
      <div className="blog-editor-toolbar"><button type="button" className={'btn'+(!preview?' primary':'')} onClick={()=>setPreview(false)}>Текст</button><button type="button" className={'btn'+(preview?' primary':'')} onClick={()=>setPreview(true)}>Попередній перегляд</button></div>
      {preview?<div className="blog-editor-preview"><h2>{form.title || 'Заголовок статті'}</h2><BlogContent body={form.body}/></div>:<><div className="blog-format-tools" aria-label="Форматування"><button type="button" onClick={()=>insert('\n## ')}>Заголовок</button><button type="button" onClick={()=>insert('**','**')}>Жирний</button><button type="button" onClick={()=>insert('*','*')}>Курсив</button><button type="button" onClick={()=>insert('\n- ')}>Список</button><button type="button" onClick={()=>insert('[','](https://)')}>Посилання</button><button type="button" onClick={()=>insert('[','](/catalog)')}>Посилання на каталог</button><button type="button" onClick={()=>insert('\n> ')}>Цитата</button><button type="button" aria-expanded={imagePicker} onClick={()=>setImagePicker(value=>!value)}>Зображення</button></div>{imagePicker && <div className="blog-inline-image"><ImageField label="Зображення для тексту статті" value={inlineImage} onChange={setInlineImage} onBusyChange={setUploading} disabled={busy}/><button className="btn" type="button" disabled={!inlineImage || uploading} onClick={()=>{insert('\n![Опис зображення]('+inlineImage+')\n');setInlineImage('');setImagePicker(false)}}>Вставити в текст</button></div>}<Field label="Текст статті" hint="Підтримується Markdown. HTML, скрипти та вбудовані фрейми не виконуються."><textarea aria-label="Текст статті" ref={text} className="input blog-source" maxLength={60000} rows={24} value={form.body} onChange={event=>set('body',event.target.value)}/></Field><p className="muted">{form.body.length} / 60000</p></>}
    </div><aside className="blog-editor-side"><Field label="Адреса статті" hint="Можна залишити порожньою для створення з назви. Старі адреси зберігаються."><input aria-label="Адреса статті" className="input" maxLength={180} value={form.slug} onChange={event=>set('slug',event.target.value)}/></Field>
      <Field label="Автор / підпис редакції"><input aria-label="Автор / підпис редакції" className="input" required maxLength={120} value={form.author_name} onChange={event=>set('author_name',event.target.value)}/></Field>
      <ImageField label="Обкладинка" value={form.cover_url} onChange={value=>set('cover_url',value)} disabled={busy} onBusyChange={setUploading}/>
      {form.cover_url && <Field label="Alt-текст обкладинки" hint="Що зображено: для пошуку в Google Картинках і читачів з екранним диктором."><input aria-label="Alt-текст обкладинки" className="input" maxLength={200} value={form.cover_alt} onChange={event=>set('cover_alt',event.target.value)}/></Field>}
      <Field label="Стан"><select aria-label="Стан" className="input" value={form.status} onChange={event=>set('status',event.target.value)}><option value="draft">Чернетка</option><option value="published">Опублікувати</option><option value="archived">Архів</option></select></Field>
      <Field label="Дата публікації" hint="За місцевим часом. Майбутня дата відкладе публікацію; порожнє поле означає публікацію зараз."><input aria-label="Дата публікації" className="input" type="datetime-local" value={form.published_at} onChange={event=>set('published_at',event.target.value)}/></Field>
      <label className="blog-check"><input type="checkbox" checked={form.comments_enabled} onChange={event=>set('comments_enabled',event.target.checked)}/>Дозволити нові коментарі</label>
      <p className="muted">Коментарі покупців завжди проходять модерацію. Закриття коментарів не видаляє наявне обговорення.</p>
      <SeoPanel form={form} set={set}/>
      <button type="submit" className="btn primary" disabled={busy || uploading}>{busy?'Зберігаємо…':form.status==='draft'?'Зберегти чернетку':form.status==='archived'?'Зберегти в архіві':form.published_at && new Date(form.published_at)>new Date()?'Запланувати публікацію':'Зберегти публікацію'}</button>
    </aside></div></fieldset></form>
    {backup && <section className="blog-recovery"><h2>Ваш попередній незбережений текст</h2><p>Порівняйте його з поточною версією та перенесіть потрібні зміни в редактор.</p><textarea className="input blog-source" readOnly value={backup} rows={10}/></section>}
  </section>
}

export default function Blog() {
  const notify=useToast()
  const [tab,setTab]=useState('posts')
  const [posts,setPosts]=useState(null)
  const [q,setQ]=useState('')
  const [search,setSearch]=useState('')
  const [status,setStatus]=useState('')
  const [page,setPage]=useState(0)
  const [editor,setEditor]=useState(null)
  const [loading,setLoading]=useState(true)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [revision,setRevision]=useState(0)
  const [pending,setPending]=useState(null)
  const [loadedKey,setLoadedKey]=useState(null)
  const [failedKey,setFailedKey]=useState(null)
  const queryKey=JSON.stringify([search,status,page])
  const currentPosts=loadedKey===queryKey?posts:null
  const waiting=loading || (loadedKey!==queryKey && failedKey!==queryKey)
  useEffect(()=>{const timer=setTimeout(()=>{setSearch(q);setPage(0)},300);return()=>clearTimeout(timer)},[q])
  useEffect(()=>{
    let active=true
    setLoading(true);setError('');setFailedKey(null)
    api.blog.posts({q:search,status,limit:20,offset:page*20})
      .then(posts=>{if(active){setPosts(posts);setPending(posts.pending_comments);setLoadedKey(queryKey)}})
      .catch(error=>{if(active){setError(error.message);setFailedKey(queryKey)}})
      .finally(()=>{if(active)setLoading(false)})
    return()=>{active=false}
  },[search,status,page,revision])
  async function open(id) {
    setBusy(true);setError('')
    try{setEditor(await api.blog.post(id))}
    catch(error){setError(error.message)}
    finally{setBusy(false)}
  }
  if(editor)return <div className="blog-admin"><Editor key={editor.id || 'new'} post={editor.id?editor:null} onClose={()=>setEditor(null)} onSaved={saved=>{setEditor(saved);setRevision(value=>value+1);notify('Статтю збережено')}}/></div>
  const tabs=[['posts','Публікації'],['comments','Коментарі'+(pending>0?' ('+pending+')':'')],['bans','Блокування'],['rules','Правила модерації']]
  return <div className="blog-admin"><header className="page-head"><div><h1>Блог</h1><p className="muted">Публікації, SEO, редакція й модероване обговорення.</p></div><div className="actions"><a className="btn" href="https://accordniche.pp.ua/blog" target="_blank" rel="noopener noreferrer">Відкрити блог</a><button className="btn primary" onClick={()=>setEditor({})}>Нова стаття</button></div></header>
    <div className="blog-admin-tabs"><div role="tablist" aria-label="Розділи блогу" className="blog-admin-tablist">{tabs.map(([key,label])=><button key={key} role="tab" aria-selected={tab===key} className="btn" onClick={()=>{setTab(key);setPage(0)}}>{label}</button>)}</div>{tab==='posts' && <button className="btn" disabled={loading || busy} onClick={()=>setRevision(value=>value+1)}>Оновити</button>}</div>
    {tab==='posts' && <><ErrorBar error={error}/><div className="blog-admin-filters"><input className="input" aria-label="Пошук статей" placeholder="Пошук за заголовком…" value={q} onChange={event=>setQ(event.target.value)}/><select className="input" aria-label="Стан статей" value={status} onChange={event=>{setStatus(event.target.value);setPage(0)}}><option value="">Усі стани</option><option value="draft">Чернетки</option><option value="published">Опубліковані й заплановані</option><option value="archived">Архів</option></select></div>
      {waiting && !currentPosts?<Loading/>:currentPosts?.items.length===0?<Empty title="Публікацій поки немає">Створіть першу статтю або змініть фільтри.</Empty>:<div className="blog-admin-posts">{currentPosts?.items.map(post=><article className="card" key={post.id}><div><span className="blog-admin-status">{state(post)}</span><h2>{post.title}</h2><p>{post.excerpt}</p><p className="muted">{date(post.published_at)} · {post.author_name} · Коментарів: {post.comment_count}</p></div><div className="actions"><button className="btn" disabled={busy} onClick={()=>open(post.id)}>Редагувати</button>{post.status==='published' && new Date(post.published_at)<=new Date() && <a className="btn" href={'https://accordniche.pp.ua/blog/'+encodeURIComponent(post.slug)} target="_blank" rel="noopener noreferrer">На сайті</a>}</div></article>)}</div>}
      {currentPosts?.total>20 && <nav className="blog-admin-pagination" aria-label="Сторінки"><button className="btn" disabled={page===0 || loading} onClick={()=>setPage(value=>value-1)}>← Назад</button><span>{page+1} / {Math.ceil(currentPosts.total/20)}</span><button className="btn" disabled={(page+1)*20>=currentPosts.total || loading} onClick={()=>setPage(value=>value+1)}>Далі →</button></nav>}</>}
    {tab==='comments' && <CommentQueue onCountsChange={counts=>setPending(counts?.pending ?? 0)}/>}
    {tab==='bans' && <BanList/>}
    {tab==='rules' && <ModerationRules/>}
  </div>
}
