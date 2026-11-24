package ua.accordniche.shop

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import ua.accordniche.shop.data.ApiException
import ua.accordniche.shop.data.MAX_CART_LINES
import ua.accordniche.shop.data.Product
import ua.accordniche.shop.data.SiteConfig
import ua.accordniche.shop.data.money
import ua.accordniche.shop.data.sanitizeCart

data class CartState(
    val cart: Map<Int, Int> = emptyMap(),
    val products: List<Product> = emptyList(),
    val loading: Boolean = false,
    val error: String = "",
    /** Per-line explanation of what changed (price, quantity). */
    val lineNotes: Map<Int, String> = emptyMap(),
    val restored: Boolean = false,
) {
    val count: Int get() = cart.values.sum()
    val lines: List<Pair<Product, Int>> get() = cart.mapNotNull { (id, qty) -> products.find { it.id == id }?.let { it to qty } }
    val unresolved: List<Int> get() = cart.keys.filter { id -> products.none { it.id == id } }
    val total get() = lines.fold(java.math.BigDecimal.ZERO) { sum, (p, q) -> sum + p.price * q.toBigDecimal() }
    /** Checkout waits until every line is re-checked against the server. */
    val blocked: Boolean get() = loading || error.isNotEmpty() || lines.size != cart.size
}

/** App-wide shop state: cart, site contacts, session bootstrap and one-line notices. */
class ShopViewModel(private val app: AppContainer) : ViewModel() {
    private val _cart = MutableStateFlow(CartState())
    val cart: StateFlow<CartState> = _cart.asStateFlow()
    private val _site = MutableStateFlow(SiteConfig())
    val site: StateFlow<SiteConfig> = _site.asStateFlow()
    private val _notice = MutableStateFlow("")
    val notice: StateFlow<String> = _notice.asStateFlow()
    val session = app.account.state
    private var validation: Job? = null
    /** Confirmation of the order just placed, shown once on the success screen. */
    var lastOrder: ua.accordniche.shop.data.CheckoutResult? = null

    init {
        viewModelScope.launch {
            _cart.update { it.copy(cart = app.cartStore.load(), restored = true) }
            validate()
        }
        viewModelScope.launch { runCatching { app.account.refresh() } }
        viewModelScope.launch { runCatching { _site.value = app.store.siteConfig() } }
        viewModelScope.launch { app.account.recordVisit() }
    }

    fun notify(message: String) { _notice.value = message }
    fun dismissNotice() { _notice.value = "" }

    /** Re-check prices and stock of everything in the cart (like the site on every visit). */
    fun validate() {
        val ids = _cart.value.cart.keys
        if (ids.isEmpty()) { _cart.update { it.copy(loading = false, error = "") }; return }
        validation?.cancel()
        validation = viewModelScope.launch {
            _cart.update { it.copy(loading = true, error = "") }
            try {
                val fresh = app.store.products(ids)
                val state = _cart.value
                val next = sanitizeCart(state.cart, fresh)
                val notes = mutableMapOf<Int, String>()
                for (product in fresh) {
                    val previous = state.products.find { it.id == product.id }
                    val before = state.cart[product.id] ?: 0
                    val after = next[product.id] ?: 0
                    val parts = buildList {
                        if (previous != null && previous.price.compareTo(product.price) != 0)
                            add("Ціна оновилась: було ${money(previous.price)}, тепер ${money(product.price)}")
                        if (after in 1 until before) add("Кількість зменшено до $after: більше немає в наявності")
                    }
                    if (parts.isNotEmpty()) notes[product.id] = parts.joinToString(". ")
                }
                val repriced = fresh.any { p -> state.products.any { it.id == p.id && it.price.compareTo(p.price) != 0 } }
                _cart.update { it.copy(cart = next, products = fresh, loading = false, lineNotes = notes) }
                if (next != state.cart) {
                    persist()
                    notify("Наявність змінилася. Недоступні позиції прибрано, кількість обмежено поточним залишком. Перевірте кошик.")
                } else if (repriced) notify("Ціни в кошику оновлено. Перевірте підсумок перед підтвердженням замовлення.")
            } catch (error: ApiException) {
                _cart.update { it.copy(loading = false, error = error.message ?: "Не вдалося перевірити кошик.") }
            }
        }
    }

    fun add(product: Product): Boolean {
        val state = _cart.value
        if (state.cart[product.id] == null && state.cart.size >= MAX_CART_LINES) {
            notify("У кошику може бути до 30 різних позицій."); return false
        }
        if (product.stock <= 0) return false
        _cart.update {
            val qty = minOf((it.cart[product.id] ?: 0) + 1, product.stock, 99)
            it.copy(cart = it.cart + (product.id to qty), products = it.products.filter { p -> p.id != product.id } + product)
        }
        persist()
        return true
    }

    fun change(id: Int, qty: Int) {
        _cart.update { state ->
            val product = state.products.find { it.id == id }
            val capped = minOf(maxOf(0, qty), product?.stock ?: 0, 99)
            state.copy(cart = if (capped > 0) state.cart + (id to capped) else state.cart - id, lineNotes = state.lineNotes - id)
        }
        persist()
    }

    fun clear() { _cart.update { it.copy(cart = emptyMap(), lineNotes = emptyMap()) }; persist() }

    private fun persist() {
        val snapshot = _cart.value.cart
        viewModelScope.launch { app.cartStore.save(snapshot) }
    }

    fun logout(done: () -> Unit = {}) {
        viewModelScope.launch {
            try {
                app.account.logout { viewModelScope.launch { app.attempts.clear() } }
                notify("Ви вийшли з профілю.")
            } catch (error: ApiException) {
                notify(error.message ?: "Не вдалося вийти. Спробуйте ще раз.")
            }
            done()
        }
    }
}
