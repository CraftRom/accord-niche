package ua.accordniche.shop.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.data.ApiException
import ua.accordniche.shop.data.Order
import ua.accordniche.shop.data.Profile

data class ProfileUi(
    val orders: List<Order> = emptyList(),
    val hasMore: Boolean = false,
    val loading: Boolean = false,
    val loadingMore: Boolean = false,
    val loaded: Boolean = false,
    val profile: Profile? = null,
    val error: String = "",
    val cancelling: Long? = null,
    val saving: Boolean = false,
    val signingIn: Boolean = false,
    // phone confirmation
    val phoneBusy: Boolean = false,
    val codeSent: Boolean = false,
    val phoneMessage: String = "",
    val telegramUrl: String = "",
    // Telegram history link
    val linkBusy: Boolean = false,
    val linkMessage: String = "",
)

class ProfileViewModel(private val app: AppContainer) : ViewModel() {
    private val _ui = MutableStateFlow(ProfileUi())
    val ui = _ui.asStateFlow()
    private var generation = 0
    private var poll: Job? = null

    fun refreshOrders() {
        if (!app.account.state.value.account.hasSession) { _ui.update { it.copy(loading = false, orders = emptyList(), profile = null, loaded = false) }; return }
        val version = ++generation
        viewModelScope.launch {
            _ui.update { it.copy(loading = true, error = "") }
            try {
                val page = app.account.orders(0)
                val profile = app.account.profile()
                if (version == generation) _ui.update { it.copy(orders = page.items, hasMore = page.hasMore, profile = profile, loaded = true) }
            } catch (error: ApiException) {
                if (version == generation) _ui.update { it.copy(error = error.message.orEmpty()) }
            } finally { if (version == generation) _ui.update { it.copy(loading = false) } }
        }
    }

    fun loadMore() {
        val state = _ui.value
        if (state.loading || state.loadingMore || !state.hasMore) return
        val version = generation
        viewModelScope.launch {
            _ui.update { it.copy(loadingMore = true, error = "") }
            try {
                val page = app.account.orders(state.orders.size)
                if (version == generation) _ui.update { it.copy(orders = (it.orders + page.items).distinctBy(Order::id), hasMore = page.hasMore) }
            } catch (error: ApiException) {
                if (version == generation) _ui.update { it.copy(error = error.message.orEmpty()) }
            } finally { _ui.update { it.copy(loadingMore = false) } }
        }
    }

    fun cancel(id: Long) {
        if (_ui.value.cancelling != null) return
        viewModelScope.launch {
            _ui.update { it.copy(cancelling = id, error = "") }
            try { app.account.cancelOrder(id); refreshOrders() }
            catch (error: ApiException) { _ui.update { it.copy(error = error.message.orEmpty()) } }
            finally { _ui.update { it.copy(cancelling = null) } }
        }
    }

    fun rename(name: String, done: () -> Unit) {
        viewModelScope.launch {
            _ui.update { it.copy(saving = true, error = "") }
            try { app.account.rename(name); done() }
            catch (error: ApiException) { _ui.update { it.copy(error = error.message.orEmpty()) } }
            finally { _ui.update { it.copy(saving = false) } }
        }
    }

    fun googleLogin(idToken: String) {
        viewModelScope.launch {
            _ui.update { it.copy(signingIn = true, error = "") }
            try { app.account.googleLogin(idToken) }
            catch (error: ApiException) { _ui.update { it.copy(error = error.message.orEmpty()) } }
            finally { _ui.update { it.copy(signingIn = false) } }
        }
    }

    fun signInFailed(message: String) = _ui.update { it.copy(error = message, signingIn = false) }
    fun startSignIn() = _ui.update { it.copy(signingIn = true, error = "") }

    /** The bot receives the user's own contact; meanwhile the profile is refreshed until it is done. */
    fun phoneViaTelegram(open: (String) -> Unit) {
        viewModelScope.launch {
            _ui.update { it.copy(phoneBusy = true, phoneMessage = "") }
            try {
                val url = app.account.phoneTelegram().url.orEmpty()
                _ui.update { it.copy(telegramUrl = url) }
                if (url.isNotEmpty()) open(url)
                poll?.cancel()
                poll = viewModelScope.launch {
                    val since = System.currentTimeMillis()
                    while (isActive) {
                        delay(3000)
                        if (System.currentTimeMillis() - since > 10 * 60 * 1000) {
                            _ui.update { it.copy(telegramUrl = "", phoneMessage = "Посилання застаріло. Натисніть «Підтвердити через Telegram» ще раз.") }
                            break
                        }
                        val verified = runCatching { app.account.refresh().account.phoneVerified }.getOrDefault(false)
                        if (verified) {
                            _ui.update { it.copy(telegramUrl = "", phoneMessage = "Номер підтверджено через Telegram.") }
                            refreshOrders(); break
                        }
                    }
                }
            } catch (error: ApiException) {
                _ui.update { it.copy(phoneMessage = error.message.orEmpty()) }
            } finally { _ui.update { it.copy(phoneBusy = false) } }
        }
    }

    fun sendCode(phone: String) {
        viewModelScope.launch {
            _ui.update { it.copy(phoneBusy = true, phoneMessage = "") }
            try { app.account.phoneSend(phone); _ui.update { it.copy(codeSent = true, phoneMessage = "Код надіслано. Введіть його з SMS нижче.") } }
            catch (error: ApiException) { _ui.update { it.copy(phoneMessage = error.message.orEmpty()) } }
            finally { _ui.update { it.copy(phoneBusy = false) } }
        }
    }

    fun checkCode(phone: String, code: String, done: () -> Unit) {
        viewModelScope.launch {
            _ui.update { it.copy(phoneBusy = true, phoneMessage = "") }
            try {
                val note = app.account.phoneCheck(phone, code)
                _ui.update { it.copy(codeSent = false, phoneMessage = note.note ?: "Номер підтверджено") }
                app.account.refresh(); refreshOrders(); done()
            } catch (error: ApiException) { _ui.update { it.copy(phoneMessage = error.message.orEmpty()) } }
            finally { _ui.update { it.copy(phoneBusy = false) } }
        }
    }

    fun linkTelegram(code: String, done: () -> Unit) {
        viewModelScope.launch {
            _ui.update { it.copy(linkBusy = true, linkMessage = "") }
            try {
                val note = app.account.linkCode(code)
                _ui.update { it.copy(linkMessage = note.note.orEmpty()) }
                app.account.refresh(); refreshOrders(); done()
            } catch (error: ApiException) { _ui.update { it.copy(linkMessage = error.message.orEmpty()) } }
            finally { _ui.update { it.copy(linkBusy = false) } }
        }
    }

    override fun onCleared() { poll?.cancel() }
}
