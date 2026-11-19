// One place for money formatting (W-37): «1 250 грн» everywhere.
const fmt = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 2 })

/** Amount with the currency: «1 250 грн». */
export const money = value => fmt.format(Number(value)) + ' грн'

/** Amount only, for places that print «грн» themselves. */
export const formatAmount = value => fmt.format(Number(value || 0))
