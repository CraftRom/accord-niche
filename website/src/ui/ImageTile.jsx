import { useEffect, useState } from 'react'

// W-38: bottles are never cropped (object-fit: contain on a light backdrop),
// the tile keeps its aspect ratio before the photo loads (no layout shift), and
// only the first-screen photo is fetched eagerly with high priority (LCP).
export function ImageTile({item, className = '', priority = false}) {
  const source = item?.image || item?.photo_url || item?.photo_endpoint || ''
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [source])
  return <div className={'photo-tile ' + className}>{source && !failed
    ? <img loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} decoding="async" src={source} alt={item.image_alt || [item.brand,item.name].filter(Boolean).join(' ')} referrerPolicy="no-referrer" onError={() => setFailed(true)}/>
    : <div className="image-unavailable"><svg viewBox="0 0 80 100" fill="none" aria-hidden="true"><path d="M29 7h22v16H29zM34 23h12v12H34zM21 35h38v55H21zM28 48h24v24H28z" stroke="currentColor" strokeWidth="1.2"/></svg><span>Зображення недоступне</span></div>}</div>
}
