package ua.accordniche.shop

import kotlinx.coroutines.runBlocking
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import ua.accordniche.shop.data.AccountRepository
import ua.accordniche.shop.data.ApiClient
import ua.accordniche.shop.data.ApiException
import ua.accordniche.shop.data.Attribution
import ua.accordniche.shop.data.CartLine
import ua.accordniche.shop.data.CatalogQuery
import ua.accordniche.shop.data.CheckoutPayload
import ua.accordniche.shop.data.QuoteRequest
import ua.accordniche.shop.data.StoreRepository
import java.math.BigDecimal
import java.util.UUID

/**
 * The whole buyer journey against a running ACCORD API (ACCORD_TEST_API=http://127.0.0.1:8765):
 * same endpoints, cookies, Origin and CSRF as the app uses. Skipped when no API is given.
 */
class LiveApiTest {
    private val base = System.getenv("ACCORD_TEST_API").orEmpty()

    private class MemoryJar : CookieJar {
        val cookies = mutableListOf<Cookie>()
        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            cookies.forEach { c -> this.cookies.removeAll { it.name == c.name }; this.cookies += c }
        }
        override fun loadForRequest(url: HttpUrl) = cookies.filter { it.matches(url) }
    }

    @Test fun `buyer journey through the website API`() = runBlocking {
        assumeTrue("ACCORD_TEST_API not set", base.isNotEmpty())
        val jar = MemoryJar()
        val api = ApiClient(base, OkHttpClient.Builder().cookieJar(jar).build())
        val store = StoreRepository(api)
        val account = AccountRepository(api) { jar.cookies.clear() }

        store.siteConfig()
        val front = store.storefront()
        assertTrue(front.total > 0)
        val page = store.aromas(CatalogQuery(sort = "price_asc"), 0)
        assertTrue(page.items.isNotEmpty() && page.brands.isNotEmpty())
        val filtered = store.aromas(CatalogQuery(brand = page.brands.first(), volume = page.volumes.first()), 0)
        assertTrue(filtered.items.all { it.brand == page.brands.first() })
        val aroma = store.aroma(page.items.first().defaultProductId).item
        val sku = aroma.variants.first { it.stock > 1 }
        assertEquals(sku.id, store.products(listOf(sku.id)).single().id)
        try { store.aroma(999999); error("expected 404") } catch (e: ApiException) { assertTrue(e.notFound) }

        account.refresh()
        assertFalse(account.state.value.account.hasSession)
        account.recordVisit()
        account.deliveryConfig()

        val quote = account.quote(QuoteRequest(listOf(CartLine(sku.id, 2)), "WELCOME10", false))
        assertEquals(0, (sku.price * BigDecimal(2)).compareTo(quote.subtotal))
        assertTrue(quote.discount > BigDecimal.ZERO)
        account.refresh()
        assertTrue("quote opens a guest session", account.state.value.account.hasSession)

        val key = UUID.randomUUID().toString().replace("-", "")
        val payload = CheckoutPayload("Шевченко", "Тарас", null, "+380671112233", "Київ", "Відділення №1", "warehouse",
            null, null, "cod", "WELCOME10", "Тест застосунку", false, true, quote.quoteToken, key, Attribution(sessionId = account.visitId))
        val result = account.checkout(payload)
        assertTrue(result.orderId > 0)
        assertEquals(0, quote.total.compareTo(result.total))
        // A retry after a lost response returns the same order, never a duplicate.
        assertEquals(result.orderId, account.checkout(payload).orderId)
        assertTrue(account.checkoutStatus(key).found)

        val orders = account.orders(0)
        assertEquals(result.orderId, orders.items.first().id)
        assertTrue(orders.items.first().canCancel)
        assertEquals(1, account.profile().ordersCount)
        assertEquals("Шевченко", account.checkoutDefaults().contactSurname)
        account.cancelOrder(result.orderId)
        assertEquals("cancelled", account.orders(0).items.first().status)

        store.posts("", 0)
        assertTrue(store.legal("terms").body.isNotBlank())

        // Without the site's Origin the server refuses a state change.
        val foreign = ApiClient("http://localhost:" + base.substringAfterLast(':'), OkHttpClient.Builder().cookieJar(jar).build())
        try { foreign.raw("POST", "/api/web/checkout/quote", "{}", "x"); error("expected 403") } catch (e: ApiException) { assertTrue(e.status in setOf(403, 422)) }

        account.logout()
        assertFalse(account.state.value.account.hasSession)
    }
}
