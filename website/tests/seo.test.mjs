import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

test('index.html asks nginx SSI for per-URL head tags and keeps one fallback',()=>{
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8')
  const head=html.split('</head>')[0]
  assert.match(head,/<!--# include virtual="\/__seo_head" stub="seo_default" -->/)
  const block=head.split('<!--# block name="seo_default" -->')[1]?.split('<!--# endblock -->')[0] || ''
  assert.equal((block.match(/<title>/g) || []).length,1,'fallback has exactly one title')
  assert.equal((head.match(/<title>/g) || []).length,1,'no second title outside the fallback')
  assert.match(block,/name="description"/)
})
test('robots.txt keeps private pages out and points to the sitemap',()=>{
  const robots=readFileSync(new URL('../public/robots.txt',import.meta.url),'utf8')
  for(const path of ['/checkout','/profile','/order/','/api/'])assert.match(robots,new RegExp('Disallow: '+path.replace('/','\\/')))
  assert.match(robots,/Sitemap: https:\/\/accordniche\.pp\.ua\/sitemap\.xml/)
})
