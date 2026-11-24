package ua.accordniche.shop.data

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

val Ukrainian: Locale = Locale.forLanguageTag("uk-UA")

private fun amountFormat() = DecimalFormat("#,##0.##", DecimalFormatSymbols(Ukrainian).apply {
    groupingSeparator = ' '; decimalSeparator = ','
})

/** «1 250 грн» everywhere, like the site. */
fun money(value: BigDecimal?): String = formatAmount(value) + " грн"

fun formatAmount(value: BigDecimal?): String =
    amountFormat().format((value ?: BigDecimal.ZERO).setScale(2, RoundingMode.HALF_UP))

fun perMl(price: BigDecimal, volume: Int): BigDecimal =
    price.divide(BigDecimal(volume), 2, RoundingMode.HALF_UP)

val genderName = mapOf("male" to "чоловічий", "female" to "жіночий", "unisex" to "унісекс")

fun parseInstant(value: String?): OffsetDateTime? {
    if (value.isNullOrBlank()) return null
    return runCatching { OffsetDateTime.parse(value) }.getOrNull()
        ?: runCatching { LocalDateTime.parse(value).atZone(ZoneId.of("UTC")).toOffsetDateTime() }.getOrNull()
}

fun formatDate(value: String?): String = parseInstant(value)
    ?.atZoneSameInstant(ZoneId.systemDefault())
    ?.format(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(Ukrainian)) ?: ""

/** Ukrainian mobile number in +380XXXXXXXXX form, or "" when it is not one. */
fun phoneNumber(raw: String): String {
    val digits = raw.filter { it in '0'..'9' }
    val body = when {
        digits.startsWith("380") -> digits.drop(3)
        digits.startsWith("80") && digits.length == 11 -> digits.drop(2)
        digits.startsWith("0") && digits.length == 10 -> digits.drop(1)
        else -> digits
    }
    return if (Regex("^[3-9][0-9]{8}$").matches(body)) "+380$body" else ""
}

/** Nova Poshta public tracking page; only for the 14-digit waybill format. */
fun trackingUrl(number: String?): String? =
    if (number != null && Regex("^\\d{14}$").matches(number)) "https://novaposhta.ua/tracking/?cargo_number=$number" else null

/** Telegram Mini App checkout link: cart as start parameter, no prices or personal data. */
fun telegramCheckoutUrl(base: String, cart: Map<Int, Int>, products: List<Product>): String {
    if (!Regex("^https://t\\.me/[A-Za-z0-9_]+/[A-Za-z0-9_]+/?$").matches(base)) return ""
    val valid = cart.filter { (id, qty) -> id > 0 && qty in 1..99 && products.any { it.id == id && it.stock >= qty } }
    if (valid.size != cart.size || valid.size > 20 || valid.isEmpty()) return ""
    val param = "cart_" + valid.entries.joinToString("-") { "${it.key}x${it.value}" }
    return if (param.length <= 512) base.trimEnd('/') + "?startapp=" + param else ""
}
