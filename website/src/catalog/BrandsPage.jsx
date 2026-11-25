import { SiteLink } from '../router'
import { Icon } from '../ui/Icon'
import { PageTitle } from '../ui/PageTitle'
import { RequestStatus } from '../ui/RequestStatus'
import { useStoreRequest } from '../useStoreRequest'

export function Brands({go}) {
  const request = useStoreRequest('/api/public/aromas?limit=1')
  return <main><PageTitle label="ПАРФУМЕРНІ БУДИНКИ" title="Бренди" detail="Бренди, представлені в актуальному каталозі."/><section className="shell"><RequestStatus request={request} empty={request.data?.brands?.length === 0}><div className="brand-grid">{request.data?.brands.map(brand => <SiteLink key={brand} to={'/catalog?brand=' + encodeURIComponent(brand)} onNavigate={go}><span>{brand}</span><Icon name="arrow" size={18}/></SiteLink>)}</div></RequestStatus></section></main>
}
