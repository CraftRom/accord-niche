import Markdown from 'react-markdown'

const elements=['p','h1','h2','h3','h4','h5','h6','strong','em','ul','ol','li','blockquote','pre','code','a','img','hr','br']
export default function BlogContent({body}) {
  return <div className="blog-prose"><Markdown skipHtml allowedElements={elements} components={{
    h1:({children})=><h2>{children}</h2>,
    a:({href,children})=><a href={href || undefined} target="_blank" rel="noopener noreferrer nofollow">{children}</a>,
    img:({src,alt})=>src && (/^https:\/\//i.test(src) || /^\/media\/[A-Za-z0-9_-]+\.(png|jpe?g|gif|webp)$/i.test(src))
      ? <img src={src} alt={alt || ''} loading="lazy" decoding="async" referrerPolicy="no-referrer"/>
      : null,
  }}>{body || ''}</Markdown></div>
}
