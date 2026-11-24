package ua.accordniche.shop

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import ua.accordniche.shop.data.ApiClient
import ua.accordniche.shop.data.ApiJson
import ua.accordniche.shop.data.CheckoutForm
import ua.accordniche.shop.data.Order
import ua.accordniche.shop.data.Product
import ua.accordniche.shop.data.checkoutErrors
import ua.accordniche.shop.data.money
import ua.accordniche.shop.data.phoneNumber
import ua.accordniche.shop.data.sanitizeCart
import ua.accordniche.shop.data.telegramCheckoutUrl
import ua.accordniche.shop.data.trackingUrl
import ua.accordniche.shop.ui.components.MdBlock
import ua.accordniche.shop.ui.components.parseMarkdown
import java.math.BigDecimal

class LogicTest {
    private fun product(id: Int, stock: Int, price: String = "100") = Product(id = id, name = "P$id", price = BigDecimal(price), stock = stock)

    @Test fun `phone numbers normalise like the site`() {
        assertEquals("+380671234567", phoneNumber("+38 (067) 123-45-67"))
        assertEquals("+380671234567", phoneNumber("0671234567"))
        assertEquals("+380671234567", phoneNumber("80671234567"))
        assertEquals("", phoneNumber("+1 555 1234"))
        assertEquals("", phoneNumber("0201234567"))
    }

    @Test fun `checkout validation names every missing field`() {
        val errors = checkoutErrors(CheckoutForm())
        assertEquals(setOf("contact_surname", "contact_name", "city", "address", "contact_phone", "terms_accepted"), errors.keys)
        val ok = CheckoutForm("Шевченко", "Тарас", "", "0671234567", "Київ", "Відділення 1", termsAccepted = true)
        assertTrue(checkoutErrors(ok).isEmpty())
        assertEquals("Заповніть поле «Адреса доставки».", checkoutErrors(ok.copy(address = " ", deliveryMethod = "courier"))["address"])
    }

    @Test fun `stored cart is capped by stock and drops unknown items`() {
        val cart = mapOf(1 to 5, 2 to 1, 3 to 120, 4 to 2)
        assertEquals(mapOf(1 to 3, 3 to 99), sanitizeCart(cart, listOf(product(1, 3), product(2, 0), product(3, 500))))
    }

    @Test fun `telegram link carries only ids and quantities`() {
        val base = "https://t.me/accord_bot/shop"
        assertEquals("$base?startapp=cart_1x2-5x1", telegramCheckoutUrl(base, linkedMapOf(1 to 2, 5 to 1), listOf(product(1, 4), product(5, 1))))
        assertEquals("", telegramCheckoutUrl(base, mapOf(1 to 5), listOf(product(1, 4))))
        assertEquals("", telegramCheckoutUrl("https://evil.example/x", mapOf(1 to 1), listOf(product(1, 4))))
    }

    @Test fun `money and tracking formats`() {
        assertEquals("1 250 грн", money(BigDecimal("1250.00")))
        assertEquals("99,5 грн", money(BigDecimal("99.50")))
        assertEquals("https://novaposhta.ua/tracking/?cargo_number=20450000000000", trackingUrl("20450000000000"))
        assertEquals(null, trackingUrl("123"))
    }

    @Test fun `decimals decode from strings and numbers`() {
        val order = ApiJson.decodeFromString(Order.serializer(), """{"id":7,"status":"new","total":630.0,"items":[{"name":"A","qty":1,"price":"630.00"}],"extra":1}""")
        assertEquals(0, BigDecimal("630").compareTo(order.total))
        assertEquals(0, BigDecimal("630").compareTo(order.items.single().price))
    }

    @Test fun `server errors keep the shop's words and field names`() {
        val validation = ApiClient.errorOf(422, """{"detail":[{"loc":["body","contact_phone"],"msg":"Value error, Використовуйте цифри 0–9 у номері телефону"}]}""")
        assertEquals("Використовуйте цифри 0–9 у номері телефону", validation.fields["contact_phone"])
        assertEquals("Замовлення вже в роботі", ApiClient.errorOf(409, """{"detail":"Замовлення вже в роботі"}""").message)
        assertTrue(ApiClient.errorOf(404, "").notFound)
    }

    @Test fun `markdown blocks`() {
        val blocks = parseMarkdown("# Title\n\nText **bold** and [link](https://x.ua).\n\n- one\n- two\n\n> quote\n\n![alt](/media/a.jpg)\n\n---")
        assertEquals(MdBlock.Heading(1, "Title"), blocks[0])
        assertTrue(blocks[1] is MdBlock.Paragraph)
        assertEquals(MdBlock.ListBlock(false, listOf("one", "two")), blocks[2])
        assertEquals(MdBlock.Quote("quote"), blocks[3])
        assertEquals(MdBlock.Image("alt", "/media/a.jpg"), blocks[4])
        assertEquals(MdBlock.Rule, blocks[5])
    }
}
