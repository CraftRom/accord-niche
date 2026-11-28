import {canAccessPage} from './roles.js'

export const LOW_STOCK=3
export const CHANNELS=[['website','Сайт'],['app','Застосунок'],['miniapp','Mini App'],['bot','Telegram-бот'],['unknown','Не визначено']]
export function orderChannel(order) {
  const {source='',channel='',session_id=''}=order.attribution || {}
  const explicit={accord_website:'website',accord_android:'app',telegram_bot:'bot',telegram_miniapp:'miniapp'}[channel]
  if(explicit)return explicit
  if(source==='accord_website')return 'website'
  if(source==='accord_android')return 'app'
  if(source==='telegram_bot')return 'bot'
  if(['telegram','miniapp','telegram_miniapp'].includes(source) || session_id)return 'miniapp'
  return 'unknown'
}
export const channelLabel=order=>CHANNELS.find(([key])=>key===orderChannel(order))[1]
const words=value=>String(value || '').trim().replace(/\s+/g,' ')
export function recipientName(order) {
  let name=words(order.contact_name)
  const surname=words(order.contact_surname),patronymic=words(order.contact_patronymic)
  if(surname && !name.startsWith(surname+' '))name=words(surname+' '+name)
  if(patronymic && !name.endsWith(' '+patronymic) && name!==patronymic)name=words(name+' '+patronymic)
  return name || 'Ім’я не вказано'
}
/** Name to show: Telegram name, else the name from the Google sign-in. */
export function customerName(user={}) {
  return (user?.first_name || '').trim() || (user?.display_name || '').trim() || (Number(user?.tg_id)<0 ? 'Покупець сайту' : 'Без імені')
}
/** Second line: email from Google, @username or Telegram id, phone. */
export function customerSubtitle(user={}) {
  const contact=user?.email || (Number(user?.tg_id)>0 ? (user.username ? '@'+user.username : `Telegram ${user.tg_id}`) : `Вебпокупець #${user?.id}`)
  return [contact, user?.phone].filter(Boolean).join(' · ')
}
export function customerContact(user={}) {
  if(Number(user?.tg_id)<=0 || !user?.tg_id)return 'Покупець сайту'
  return user.username?'@'+user.username:'Telegram підключено'
}
export function phoneHref(value) {
  const clean=String(value || '').replace(/[\s().-]/g,'')
  return /^\+?[0-9]{5,15}$/.test(clean)?'tel:'+clean:undefined
}
export function paymentMeta(method) {
  return {cod:{title:'Оплата при отриманні',hint:'Накладений платіж',icon:'📦'},card:{title:'Переказ за реквізитами',hint:'Після підтвердження менеджером',icon:'💳'}}[method] || {title:'Спосіб оплати не вказано',hint:'Уточніть у покупця',icon:'?'}
}
export function inventoryState(product) {
  if(!product.is_active)return {tone:'hidden',label:'Прихований'}
  if(Number(product.price)<=0)return {tone:'bad',label:'Без ціни'}
  if(Number(product.stock)<=0)return {tone:'bad',label:'Немає в наявності'}
  if(Number(product.stock)<=LOW_STOCK)return {tone:'warn',label:'Закінчується'}
  return {tone:'ok',label:'У наявності'}
}
export function publicationState(product) {
  const visible=Boolean(product.is_active && Number(product.price)>0 && String(product.name || '').trim())
  const buyable=visible && Number(product.stock)>0
  return {visible,buyable,label:!visible?'Не опубліковано на сайті':buyable?'Доступний на сайті':'На сайті, немає в наявності'}
}
export const INVENTORY=[['available','У наявності'],['low','Залишок до 3 шт.'],['out','Немає в наявності'],['unpriced','Активні без ціни'],['missing_photos','Без зображення'],['hidden','Приховані']]

const groups=[
  {title:'Продажі',items:[['/','Огляд магазину'],['/orders','Замовлення','orders'],['/customers','Клієнти'],['/support','Підтримка','support']]},
  {title:'Вітрина й контент',items:[['/catalog','Товари та залишки'],['/blog','Блог'],['/documents','Документи']]},
  {title:'Маркетинг',items:[['/promos','Промокоди'],['/broadcasts','Розсилки']]},
  {title:'Керування',items:[['/store-audit','Контроль магазину'],['/operators','Команда та доступ'],['/settings','Налаштування'],['/logs','Журнал'],['/backups','Резервні копії'],['/instructions','Інструкції']]},
]
export function navigationFor(role) {
  return groups.map(group=>({...group,items:group.items.filter(([to])=>canAccessPage(role,to)).map(([to,label,badge])=>({to,label,badge,end:to==='/'}))})).filter(group=>group.items.length)
}
