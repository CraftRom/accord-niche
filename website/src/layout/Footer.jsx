import { Logo } from './Header'
import { SiteLink } from '../router'

// W-26: four groups a buyer scans in seconds; delivery, returns and contacts
// are at most two clicks away. Legal links come only from configuration.
export function Footer({go, setInfo, site}) {
  const phone = site.phone ? site.phone.replace(/[^+\d]/g, '') : ''
  const support = [site.phone && <a key="phone" href={'tel:' + phone}>{site.phone}</a>, site.email && <a key="email" href={'mailto:' + site.email}>{site.email}</a>,
    site.instagram_url && <a key="ig" href={site.instagram_url} target="_blank" rel="noopener noreferrer">Instagram</a>,
    site.tiktok_url && <a key="tt" href={site.tiktok_url} target="_blank" rel="noopener noreferrer">TikTok</a>].filter(Boolean)
  const docs = [site.terms_url && <a key="terms" href={site.terms_url} target="_blank" rel="noopener noreferrer">Умови покупки</a>,
    site.privacy_url && <a key="privacy" href={site.privacy_url} target="_blank" rel="noopener noreferrer">Політика конфіденційності</a>].filter(Boolean)
  return <footer className="footer"><div className="shell footer-inner"><div className="footer-brand"><Logo dark onClick={() => go('/')}/><span>accordniche.pp.ua</span>{site.seller_name && <span>{site.seller_name}</span>}</div>
    <nav className="footer-links" aria-label="Інформація для покупців">
      <div><h2>Покупцям</h2><SiteLink to="/catalog" onNavigate={go}>Каталог</SiteLink><button onClick={() => setInfo('delivery')}>Доставка й оплата</button><button onClick={() => setInfo('returns')}>Повернення та скасування</button><SiteLink to="/how" onNavigate={go}>Як це працює</SiteLink></div>
      <div><h2>Про магазин</h2><SiteLink to="/brands" onNavigate={go}>Бренди</SiteLink><SiteLink to="/blog" onNavigate={go}>Блог</SiteLink><SiteLink to="/profile" onNavigate={go}>Особистий кабінет</SiteLink></div>
      {support.length > 0 && <div><h2>Підтримка</h2>{support}</div>}
      {docs.length > 0 && <div><h2>Документи</h2>{docs}</div>}
    </nav></div></footer>
}
