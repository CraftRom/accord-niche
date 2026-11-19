export const SETTINGS_CATEGORIES = [
  { id: 'store', label: 'Магазин і доставка' },
  { id: 'loyalty', label: 'Бонуси та знижки' },
  { id: 'automation', label: 'Автовідповіді' },
  { id: 'integrations', label: 'Інтеграції' },
  { id: 'access', label: 'Доступ і Telegram' },
  { id: 'system', label: 'Система' },
]

export function categoryFor(title) {
  if (['Магазин', 'Доставка', 'Реквізити продавця', 'Оплата', 'Посилання на сайті'].includes(title)) return 'store'
  if (['Бонуси', 'Реферальна програма', 'Знижка за суму'].includes(title)) return 'loyalty'
  if (title === 'Автовідповіді') return 'automation'
  if (['SalesDrive', 'Вхід через Google', 'SMS-підтвердження (Twilio Verify)'].includes(title)) return 'integrations'
  if (['Telegram-група', 'Бот і Mini App'].includes(title)) return 'access'
  return 'system'
}

export function changedSettings(form, initial, allowed) {
  if (!form || !initial) return {}
  return Object.fromEntries([...allowed]
    .filter((key) => form[key] !== undefined && String(form[key]) !== String(initial[key]))
    .map((key) => [key, form[key]]))
}

/** Fields hidden until «Показати додаткові параметри» (searching shows them too). */
export function visibleItems(group, { expanded = false, searching = false } = {}) {
  return expanded || searching ? group.items : group.items.filter((item) => !item.advanced)
}
