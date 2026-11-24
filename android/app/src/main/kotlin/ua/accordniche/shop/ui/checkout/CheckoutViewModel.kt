package ua.accordniche.shop.ui.checkout

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.CartState
import ua.accordniche.shop.data.ApiException
import ua.accordniche.shop.data.AttemptLine
import ua.accordniche.shop.data.Attribution
import ua.accordniche.shop.data.CartLine
import ua.accordniche.shop.data.CheckoutAttempt
import ua.accordniche.shop.data.CheckoutForm
import ua.accordniche.shop.data.CheckoutPayload
import ua.accordniche.shop.data.CheckoutResult
import ua.accordniche.shop.data.DeliveryConfig
import ua.accordniche.shop.data.DirectoryItem
import ua.accordniche.shop.data.Quote
import ua.accordniche.shop.data.QuoteRequest
import ua.accordniche.shop.data.checkoutErrors
import ua.accordniche.shop.data.phoneNumber
import java.util.UUID

data class CheckoutUi(
    val form: CheckoutForm = CheckoutForm(),
    val errors: Map<String, String> = emptyMap(),
    val quote: Quote? = null,
    val quoteSignature: String = "",
    val quoting: Boolean = false,
    val submitting: Boolean = false,
    val checking: Boolean = false,
    val error: String = "",
    val delivery: DeliveryConfig = DeliveryConfig(),
    val cityOptions: List<DirectoryItem> = emptyList(),
    val warehouseOptions: List<DirectoryItem> = emptyList(),
    val directoryBusy: String = "",
    val deliveryNote: String = "",
    val cityRef: String = "",
    val settlementRef: String = "",
    val warehouseRef: String = "",
    val attempt: CheckoutAttempt? = null,
    val attemptLoaded: Boolean = false,
    val result: CheckoutResult? = null,
) {
    val locked get() = attempt != null || submitting
}

/** Website checkout, step for step: quote → confirm with a durable idempotency key. */
class CheckoutViewModel(private val app: AppContainer) : ViewModel() {
    private val _ui = MutableStateFlow(CheckoutUi())
    val ui = _ui.asStateFlow()
    private var cart = CartState()
    private var pristine = true
    private var quoteJob: Job? = null
    private var cityJob: Job? = null
    private var warehouseJob: Job? = null
    private var quoteSequence = 0

    private val lines get() = cart.lines.filter { it.second > 0 }
    private val blocked get() = cart.blocked
    private fun signature(form: CheckoutForm = _ui.value.form) =
        lines.joinToString(";") { "${it.first.id}x${it.second}@${it.first.price.toPlainString()}" } + "|" + form.promoCode.trim() + "|" + form.useBonus

    val currentQuote: Quote? get() = _ui.value.let { if (it.quoteSignature == signature(it.form)) it.quote else null }

    init {
        viewModelScope.launch {
            val attempt = app.attempts.read()
            _ui.update { it.copy(attempt = attempt, attemptLoaded = true, form = attempt?.let { a -> CheckoutForm.of(a.payload) } ?: it.form,
                cityRef = attempt?.payload?.deliveryCityRef.orEmpty(), warehouseRef = attempt?.payload?.deliveryWarehouseRef.orEmpty()) }
            if (attempt != null) pristine = false
            runCatching { app.account.refresh() }
            if (attempt != null) recover()
            val config = runCatching { app.account.deliveryConfig() }
            config.onSuccess { c -> _ui.update { it.copy(delivery = c) } }
                .onFailure { _ui.update { it.copy(deliveryNote = "Довідник доставки тимчасово недоступний. Введіть адресу вручну.") } }
            loadDefaults()
        }
    }

    private suspend fun loadDefaults() {
        if (!app.account.state.value.account.hasSession || _ui.value.attempt != null) return
        val data = runCatching { app.account.checkoutDefaults() }.getOrNull() ?: return
        if (!pristine) return
        val method = if (data.deliveryMethod == "courier" && _ui.value.delivery.courierEnabled) "courier" else "warehouse"
        val compatible = data.deliveryMethod.isEmpty() || data.deliveryMethod == method
        _ui.update { it.copy(
            form = it.form.copy(contactSurname = data.contactSurname, contactName = data.contactName, contactPatronymic = data.contactPatronymic,
                contactPhone = data.contactPhone, city = data.city, address = if (compatible) data.address else "", deliveryMethod = method,
                paymentMethod = if (data.paymentMethod in setOf("cod", "card")) data.paymentMethod else "cod"),
            cityRef = data.deliveryCityRef, warehouseRef = if (compatible && method == "warehouse") data.deliveryWarehouseRef else "") }
    }

    /** Called whenever the shared cart changes (validated lines and prices). */
    fun onCart(state: CartState) {
        cart = state
        scheduleQuote()
    }

    fun update(transform: (CheckoutForm) -> CheckoutForm, vararg cleared: String) {
        pristine = false
        _ui.update { it.copy(form = transform(it.form), errors = it.errors - cleared.toSet()) }
        scheduleQuote()
    }

    fun setCity(value: String) {
        update({ it.copy(city = value, address = "") }, "city", "address")
        _ui.update { it.copy(cityRef = "", settlementRef = "", warehouseRef = "", warehouseOptions = emptyList()) }
        searchCities()
    }

    fun setAddress(value: String) {
        update({ it.copy(address = value) }, "address")
        _ui.update { it.copy(warehouseRef = "") }
        searchWarehouses()
    }

    fun setMethod(method: String) {
        update({ it.copy(deliveryMethod = method, address = "") }, "address")
        _ui.update { it.copy(warehouseRef = "", warehouseOptions = emptyList()) }
        searchWarehouses()
    }

    fun pickCity(item: DirectoryItem) {
        update({ it.copy(city = item.label, address = "") }, "city", "address")
        _ui.update { it.copy(cityRef = item.ref, settlementRef = item.settlementRef.orEmpty(), warehouseRef = "", cityOptions = emptyList()) }
        searchWarehouses()
    }

    fun pickWarehouse(item: DirectoryItem) {
        update({ it.copy(address = item.label) }, "address")
        _ui.update { it.copy(warehouseRef = item.ref, warehouseOptions = emptyList()) }
    }

    fun closeSuggestions() = _ui.update { it.copy(cityOptions = emptyList(), warehouseOptions = emptyList()) }

    private fun searchCities() {
        cityJob?.cancel()
        val ui = _ui.value
        _ui.update { it.copy(cityOptions = emptyList()) }
        if (!ui.delivery.novaposhtaEnabled || ui.cityRef.isNotEmpty() || ui.form.city.trim().length < 2 || ui.locked) return
        cityJob = viewModelScope.launch {
            delay(350)
            _ui.update { it.copy(directoryBusy = "city") }
            try {
                val result = app.account.cities(_ui.value.form.city.trim())
                _ui.update { it.copy(cityOptions = result.items.take(12), deliveryNote = if (result.manual) "Довідник недоступний. Введіть населений пункт і адресу вручну." else "") }
            } catch (error: ApiException) {
                _ui.update { it.copy(deliveryNote = "Не вдалося завантажити міста. Доступне ручне введення.") }
            } finally { _ui.update { it.copy(directoryBusy = "") } }
        }
    }

    private fun searchWarehouses() {
        warehouseJob?.cancel()
        val ui = _ui.value
        _ui.update { it.copy(warehouseOptions = emptyList()) }
        if (!ui.delivery.novaposhtaEnabled || ui.form.deliveryMethod != "warehouse" || (ui.cityRef.isEmpty() && ui.settlementRef.isEmpty()) ||
            ui.warehouseRef.isNotEmpty() || ui.locked) return
        warehouseJob = viewModelScope.launch {
            delay(350)
            _ui.update { it.copy(directoryBusy = "warehouse") }
            try {
                val now = _ui.value
                val result = app.account.warehouses(now.cityRef, now.settlementRef, now.form.address)
                _ui.update { it.copy(warehouseOptions = result.items.take(15), deliveryNote = if (result.manual) "Довідник недоступний. Вкажіть відділення або поштомат вручну." else "") }
            } catch (error: ApiException) {
                _ui.update { it.copy(deliveryNote = "Не вдалося завантажити відділення. Доступне ручне введення.") }
            } finally { _ui.update { it.copy(directoryBusy = "") } }
        }
    }

    private fun scheduleQuote() {
        quoteJob?.cancel()
        if (_ui.value.attempt != null || blocked || lines.isEmpty() || currentQuote != null) return
        quoteJob = viewModelScope.launch { delay(400); preview() }
    }

    suspend fun preview(): Quote? {
        val ui = _ui.value
        if (blocked || lines.isEmpty() || ui.attempt != null || ui.submitting) return null
        val sequence = ++quoteSequence
        val captured = signature(ui.form)
        _ui.update { it.copy(quoting = true, error = "") }
        return try {
            val quote = app.account.quote(QuoteRequest(lines.map { CartLine(it.first.id, it.second) }, ui.form.promoCode.trim().ifEmpty { null }, ui.form.useBonus))
            if (sequence == quoteSequence && signature() == captured) {
                _ui.update { it.copy(quote = quote, quoteSignature = captured) }
                runCatching { app.account.refresh() }
            }
            quote
        } catch (error: ApiException) {
            if (sequence == quoteSequence && signature() == captured) _ui.update { it.copy(quote = null, quoteSignature = "", error = error.message.orEmpty()) }
            null
        } finally {
            if (sequence == quoteSequence) _ui.update { it.copy(quoting = false) }
        }
    }

    fun recalculate() { viewModelScope.launch { preview() } }

    private suspend fun finish(result: CheckoutResult, onDone: () -> Unit) {
        if (result.orderId <= 0) {
            _ui.update { it.copy(error = "Не вдалося перевірити номер замовлення. Повторіть перевірку.") }; return
        }
        app.attempts.clear()
        _ui.update { it.copy(attempt = null, result = result) }
        onDone()
    }

    var onComplete: (CheckoutResult) -> Unit = {}

    fun recover() {
        val attempt = _ui.value.attempt ?: return
        if (_ui.value.checking || _ui.value.submitting) return
        viewModelScope.launch {
            _ui.update { it.copy(checking = true, error = "") }
            try {
                val result = app.account.checkoutStatus(attempt.payload.checkoutKey)
                if (result.found) finish(result) { onComplete(result) }
            } catch (error: ApiException) {
                _ui.update { it.copy(error = error.message.orEmpty()) }
                if (error.status == 401) { app.attempts.clear(); _ui.update { it.copy(attempt = null, form = CheckoutForm()) } }
            } finally { _ui.update { it.copy(checking = false) } }
        }
    }

    /** Returns the field to focus when validation fails. */
    fun submit(onInvalid: (String) -> Unit) {
        val ui = _ui.value
        if (ui.submitting || ui.quoting || ui.checking) return
        viewModelScope.launch {
            var outgoing = _ui.value.attempt
            if (outgoing == null) {
                if (blocked || lines.isEmpty()) return@launch
                val quote = currentQuote ?: run { preview(); return@launch }
                val form = _ui.value.form
                val errors = checkoutErrors(form)
                _ui.update { it.copy(errors = errors) }
                if (errors.isNotEmpty()) {
                    _ui.update { it.copy(error = "Перевірте позначені поля. Ваші дані збережено у формі.") }
                    onInvalid(errors.keys.first()); return@launch
                }
                val state = _ui.value
                val payload = CheckoutPayload(
                    contactSurname = form.contactSurname.trim(), contactName = form.contactName.trim(),
                    contactPatronymic = form.contactPatronymic.trim().ifEmpty { null }, contactPhone = phoneNumber(form.contactPhone),
                    city = form.city.trim(), address = form.address.trim(), deliveryMethod = form.deliveryMethod,
                    deliveryCityRef = state.cityRef.ifEmpty { null },
                    deliveryWarehouseRef = if (form.deliveryMethod == "warehouse") state.warehouseRef.ifEmpty { null } else null,
                    paymentMethod = form.paymentMethod, promoCode = form.promoCode.trim().ifEmpty { null }, comment = form.comment.trim().ifEmpty { null },
                    useBonus = form.useBonus, termsAccepted = true, quoteToken = quote.quoteToken,
                    checkoutKey = UUID.randomUUID().toString().replace("-", ""),
                    attribution = Attribution(sessionId = app.account.visitId),
                )
                val attempt = CheckoutAttempt(payload, lines.map { (product, qty) ->
                    AttemptLine(product.copy(price = quote.items.find { it.productId == product.id }?.unitPrice ?: product.price), qty)
                }, quote.total)
                app.attempts.remember(attempt)
                _ui.update { it.copy(attempt = attempt) }
                outgoing = attempt
            }
            _ui.update { it.copy(submitting = true, error = "") }
            try {
                val result = app.account.checkout(outgoing.payload)
                finish(result) { onComplete(result) }
            } catch (error: ApiException) {
                _ui.update { it.copy(error = error.message.orEmpty()) }
                // A definite refusal: unlock the form. A lost connection keeps the attempt for a safe retry.
                if (error.status in 400..499) {
                    app.attempts.clear()
                    _ui.update { it.copy(attempt = null, quote = null, quoteSignature = "",
                        errors = error.fields.filterKeys { it in FIELDS }, form = if (error.status == 401) CheckoutForm() else it.form) }
                }
            } finally { _ui.update { it.copy(submitting = false) } }
        }
    }

    companion object {
        val FIELDS = setOf("contact_surname", "contact_name", "contact_patronymic", "contact_phone", "city", "address", "promo_code", "terms_accepted")
    }
}
