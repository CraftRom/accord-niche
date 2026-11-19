/** Документи вітрини.
 *
 * Тексти публічної оферти й політики конфіденційності тепер одні для сайту й
 * Mini App: їх редагують у панелі («Документи»), а сервер підставляє
 * реквізити продавця (SELLER_NAME, SELLER_CODE, SELLER_ADDRESS, SELLER_EMAIL,
 * SELLER_PHONE) і віддає готовий текст: GET /api/shop/legal/{terms|privacy}.
 * Повернення й обмін — розділ оферти, тож пункт «Повернення» відкриває її.
 */

export const DOCUMENTS = [
  { key: 'offer', source: 'terms', title: 'Публічна оферта' },
  { key: 'privacy', source: 'privacy', title: 'Політика конфіденційності' },
  { key: 'returns', source: 'terms', title: 'Повернення та обмін', section: '## 8.' },
]

export function documentFor(key) {
  return DOCUMENTS.find((doc) => doc.key === key) || DOCUMENTS[0]
}

/** Розбирає обмежений Markdown документа (## заголовки, списки, **жирний**)
 *  у безпечні блоки. HTML не інтерпретується: текст лишається текстом. */
export function blocks(markdown) {
  const out = []
  for (const chunk of String(markdown || '').split(/\n{2,}/)) {
    const text = chunk.trim()
    if (!text) continue
    if (text.startsWith('## ')) { out.push({ type: 'h', text: text.slice(3).trim() }); continue }
    const lines = text.split('\n')
    if (lines.every((line) => line.startsWith('- '))) { out.push({ type: 'ul', items: lines.map((line) => line.slice(2)) }); continue }
    out.push({ type: 'p', lines })
  }
  return out
}

/** «**жирний**» → частини для рендерингу без dangerouslySetInnerHTML. */
export function inline(text) {
  return String(text).split(/(\*\*[^*]+\*\*)/).filter(Boolean)
    .map((part) => part.startsWith('**') && part.endsWith('**') ? { bold: true, text: part.slice(2, -2) } : { bold: false, text: part })
}
