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
test('aroma links use the readable canonical address and keep old numeric links working',async()=>{
  const {aromaPath,AROMA_ROUTE}=await import('../src/catalog/aromaPath.js')
  const group={id:7,default_product_id:9,slug:'creed-aventus',path:'/aroma/7-creed-aventus'}
  assert.equal(aromaPath(group),'/aroma/7-creed-aventus')
  assert.equal(aromaPath(group,9),'/aroma/9-creed-aventus')
  assert.equal(aromaPath({id:3,default_product_id:4}),'/aroma/4','older API without slug')
  assert.equal('/aroma/7'.match(AROMA_ROUTE)[1],'7')
  assert.equal('/aroma/7-creed-aventus'.match(AROMA_ROUTE)[1],'7')
  assert.equal('/aroma/7-<script>'.match(AROMA_ROUTE),null)
})
test('robots.txt allows product photos and the dashboard and Mini App are never indexed',()=>{
  const robots=readFileSync(new URL('../public/robots.txt',import.meta.url),'utf8')
  assert.match(robots,/Allow: \/api\/public\/catalog\/\*\/photo/)
  for(const app of ['dashboard','miniapp']){
    const html=readFileSync(new URL('../../'+app+'/index.html',import.meta.url),'utf8')
    assert.match(html,/<meta name="robots" content="noindex, nofollow, noarchive" \/>/)
    const conf=readFileSync(new URL('../../deploy/nginx/accord-domain-'+app+'.conf',import.meta.url),'utf8')
    assert.match(conf,/add_header X-Robots-Tag "noindex, nofollow, noarchive, nosnippet" always;/)
    assert.match(conf,/location = \/robots\.txt \{[^}]*Disallow: \//)
  }
})
