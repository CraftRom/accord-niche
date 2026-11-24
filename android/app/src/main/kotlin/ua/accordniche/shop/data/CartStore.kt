package ua.accordniche.shop.data

import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer

private val Context.cartStore by preferencesDataStore("accord_cart")
private val Context.checkoutStore by preferencesDataStore("accord_checkout")
private val CART = stringPreferencesKey("cart")
private val ATTEMPT = stringPreferencesKey("attempt")
private val cartSerializer = MapSerializer(String.serializer(), Int.serializer())

/** The cart lives on this device, like the site's localStorage cart. */
class CartStore(private val context: Context) {
    suspend fun load(): Map<Int, Int> = context.cartStore.data.map { prefs ->
        runCatching { ApiJson.decodeFromString(cartSerializer, prefs[CART] ?: "{}") }.getOrDefault(emptyMap())
            .mapNotNull { (id, qty) -> id.toIntOrNull()?.takeIf { it > 0 && qty > 0 }?.let { it to qty } }
            .take(MAX_CART_LINES).toMap()
    }.first()

    suspend fun save(cart: Map<Int, Int>) {
        context.cartStore.edit { it[CART] = ApiJson.encodeToString(cartSerializer, cart.mapKeys { (id, _) -> id.toString() }) }
    }
}

/** A submitted, not yet confirmed order: survives app restarts so a retry reuses its key. */
class CheckoutAttemptStore(private val context: Context) {
    suspend fun read(): CheckoutAttempt? = context.checkoutStore.data.map { prefs ->
        prefs[ATTEMPT]?.let { raw ->
            runCatching { ApiJson.decodeFromString(CheckoutAttempt.serializer(), raw) }.getOrNull()
                ?.takeIf { it.lines.isNotEmpty() && Regex("^[A-Za-z0-9_-]{12,64}$").matches(it.payload.checkoutKey) }
        }
    }.first()

    suspend fun remember(attempt: CheckoutAttempt) {
        context.checkoutStore.edit { it[ATTEMPT] = ApiJson.encodeToString(CheckoutAttempt.serializer(), attempt) }
    }

    suspend fun clear() { context.checkoutStore.edit { it.remove(ATTEMPT) } }
}
