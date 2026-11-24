package ua.accordniche.shop.data

data class CheckoutForm(
    val contactSurname: String = "",
    val contactName: String = "",
    val contactPatronymic: String = "",
    val contactPhone: String = "",
    val city: String = "",
    val address: String = "",
    val deliveryMethod: String = "warehouse",
    val paymentMethod: String = "cod",
    val promoCode: String = "",
    val comment: String = "",
    val termsAccepted: Boolean = false,
    val useBonus: Boolean = false,
) {
    companion object {
        fun of(payload: CheckoutPayload) = CheckoutForm(
            payload.contactSurname, payload.contactName, payload.contactPatronymic.orEmpty(), payload.contactPhone,
            payload.city, payload.address, payload.deliveryMethod, payload.paymentMethod, payload.promoCode.orEmpty(),
            payload.comment.orEmpty(), payload.termsAccepted, payload.useBonus,
        )
    }
}

/** The same field checks as the website, before anything is sent. */
fun checkoutErrors(form: CheckoutForm): Map<String, String> {
    val errors = linkedMapOf<String, String>()
    val required = listOf(
        Triple("contact_surname", "Прізвище", 64) to form.contactSurname,
        Triple("contact_name", "Ім’я", 128) to form.contactName,
        Triple("city", "Населений пункт", 128) to form.city,
        Triple("address", if (form.deliveryMethod == "courier") "Адреса доставки" else "Відділення або поштомат", 255) to form.address,
    )
    for ((rule, value) in required) {
        val (field, label, max) = rule
        if (value.isBlank()) errors[field] = "Заповніть поле «$label»."
        else if (value.trim().length > max) errors[field] = "Не більше $max символів."
    }
    if (phoneNumber(form.contactPhone).isEmpty()) errors["contact_phone"] = "Вкажіть український номер, наприклад +380671234567."
    val fullName = listOf(form.contactSurname, form.contactName, form.contactPatronymic)
        .map { it.trim() }.filter { it.isNotEmpty() }.joinToString(" ")
    if (fullName.length > 255) errors["contact_name"] = "Скоротіть ПІБ: загалом не більше 255 символів."
    if (!form.termsAccepted) errors["terms_accepted"] = "Підтвердьте згоду з умовами покупки."
    return errors
}

/** Untrusted stored cart: unknown SKUs dropped, quantities capped by stock and 99. */
fun sanitizeCart(cart: Map<Int, Int>, products: List<Product>): Map<Int, Int> {
    val byId = products.associateBy { it.id }
    val valid = linkedMapOf<Int, Int>()
    for ((id, qty) in cart.entries.take(MAX_CART_LINES)) {
        val product = byId[id] ?: continue
        if (id <= 0 || qty <= 0) continue
        val capped = minOf(qty, 99, maxOf(0, product.stock))
        if (capped > 0) valid[id] = capped
    }
    return valid
}

const val MAX_CART_LINES = 30
