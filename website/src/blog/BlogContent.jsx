import Markdown from 'react-markdown'

const elements=['p','h1','h2','h3','h4','h5','h6','strong','em','ul','ol','li','blockquote','pre','code','a','img','hr','br']
// Links to the shop itself stay in the same tab and are followed by crawlers
// (internal linking); links to other sites open in a new tab.
const internal=href=>/^\/(?!\/)/.test(href || '') || /^https:\/\/accordniche\.pp\.ua(\/|$)/i.test(href || '')
export default function BlogContent({body,go}) {
  return <div className="blog-prose"><Markdown skipHtml allowedElements={elements} components={{
    h1:({children})=><h2>{children}</h2>,
    a:({href,children})=>internal(href)
      ? <a href={href.replace(/^https:\/\/accordniche\.pp\.ua/i,'') || '/'} onClick={event=>{if(!go || event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)return;event.preventDefault();go(href.replace(/^https:\/\/accordniche\.pp\.ua/i,'') || '/')}}>{children}</a>
      : <a href={href || undefined} target="_blank" rel="noopener noreferrer nofollow">{children}</a>,
    img:({src,alt})=>src && (/^https:\/\//i.test(src) || /^\/media\/[A-Za-z0-9_-]+\.(png|jpe?g|gif|webp)$/i.test(src))
      ? <img src={src} alt={alt || ''} loading="lazy" decoding="async" referrerPolicy="no-referrer"/>
      : null,
  }}>{body || ''}</Markdown></div>
}
