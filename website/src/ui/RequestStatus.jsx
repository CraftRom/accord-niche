import { StateBlock, errorTitle } from './states'

export function RequestStatus({request, empty, children}) {
  if (!request.data && request.loading) return <StateBlock kind="loading" className="store-loading">Завантажуємо товари…</StateBlock>
  if (!request.data && request.error) return <StateBlock kind="error" className="store-state" title={errorTitle(request, 'Товар недоступний')}
    action={<button className="btn outline" onClick={request.retry}>Спробувати ще раз</button>}><p>{request.error}</p></StateBlock>
  return <>{request.error && <div className="notice" role="alert">Не вдалося оновити дані. Показуємо останню завантажену версію. <button onClick={request.retry}>Оновити</button></div>}{empty ? <StateBlock className="store-state" title="Поки немає товарів"><p>Перегляньте інші добірки або завітайте пізніше.</p></StateBlock> : children}</>
}
