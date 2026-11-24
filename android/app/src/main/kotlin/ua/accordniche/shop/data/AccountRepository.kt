package ua.accordniche.shop.data

import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import java.net.URLEncoder
import java.util.UUID

data class SessionState(
    val account: Account = Account(),
    val googleClientId: String = "",
    val smsEnabled: Boolean = false,
    val telegramPhone: Boolean = false,
    val ready: Boolean = false,
)

@Serializable private data class GoogleIn(val credential: String)
@Serializable private data class NameIn(@SerialName("display_name") val displayName: String)
@Serializable private data class PhoneIn(val phone: String)
@Serializable private data class PhoneCheckIn(val phone: String, val code: String)
@Serializable private data class CodeIn(val code: String)
@Serializable private data class CommentIn(val body: String, @SerialName("parent_id") val parentId: Int?, @SerialName("client_key") val clientKey: String)
@Serializable private data class CommentEditIn(val body: String, val version: Int)
@Serializable private data class VersionIn(val version: Int)
@Serializable private data class VisitIn(@SerialName("session_id") val sessionId: String, val attribution: Attribution)

/**
 * The buyer's website account (/api/web): guest session, Google sign-in,
 * checkout, orders, phone confirmation and blog comments.
 */
class AccountRepository(private val api: ApiClient, private val clearCookies: () -> Unit) {
    private val _state = MutableStateFlow(SessionState())
    val state: StateFlow<SessionState> = _state.asStateFlow()
    private var csrf: String = ""
    private val sessionLock = Mutex()

    /** One anonymous id per app launch for the visit → order funnel. */
    val visitId: String = UUID.randomUUID().toString().replace("-", "")
    private var visitSent = false

    suspend fun refresh(): SessionState = sessionLock.withLock {
        try {
            val session: WebSession = api.get("/api/web/session")
            csrf = session.csrf
            _state.value = SessionState(session.account, session.googleClientId, session.phoneSmsEnabled, session.phoneTelegramEnabled, true)
        } catch (error: ApiException) {
            _state.update { it.copy(ready = true) }
            throw error
        }
        _state.value
    }

    private suspend fun ensureCsrf() { if (csrf.isEmpty()) refresh() }

    private fun signedOut() {
        csrf = ""
        _state.update { it.copy(account = Account()) }
    }

    private suspend inline fun <T> guarded(block: () -> T): T = try {
        block()
    } catch (error: ApiException) {
        if (error.status == 401) signedOut()
        // A stale CSRF pair (cookie expired): fetch a fresh one for the next try.
        if (error.status == 403 && error.message?.contains("Оновіть") == true) csrf = ""
        throw error
    }

    suspend inline fun <reified T> webGet(path: String): T = webGetRaw(path).let { ApiJson.decodeFromString(it.ifEmpty { "{}" }) }

    suspend fun webGetRaw(path: String): String = guarded { api.raw("GET", "/api/web$path") }

    suspend fun webSend(method: String, path: String, body: String? = null): String {
        ensureCsrf()
        return guarded { api.raw(method, "/api/web$path", body, csrf) }
    }

    suspend inline fun <reified T, reified B> webSend(method: String, path: String, body: B): T =
        ApiJson.decodeFromString(webSend(method, path, ApiJson.encodeToString(body)).ifEmpty { "{}" })

    // --- identity ---
    suspend fun googleLogin(idToken: String) {
        webSend("POST", "/auth/google", ApiJson.encodeToString(GoogleIn(idToken)))
        refresh()
    }

    suspend fun logout(onDone: () -> Unit = {}) {
        try { webSend("POST", "/auth/logout") } finally {
            clearCookies(); csrf = ""; onDone()
            runCatching { refresh() }
        }
    }

    suspend fun profile(): Profile = webGet("/profile")
    suspend fun orders(offset: Int): OrderPage = webGet("/orders?limit=30&offset=$offset")
    suspend fun cancelOrder(id: Long) { webSend("POST", "/orders/$id/cancel") }
    suspend fun rename(name: String) { webSend("PATCH", "/profile", ApiJson.encodeToString(NameIn(name.trim()))); refresh() }
    suspend fun phoneTelegram(): Note = ApiJson.decodeFromString(webSend("POST", "/profile/phone/telegram"))
    suspend fun phoneSend(phone: String) { webSend("POST", "/profile/phone/send", ApiJson.encodeToString(PhoneIn(phone))) }
    suspend fun phoneCheck(phone: String, code: String): Note =
        ApiJson.decodeFromString(webSend("POST", "/profile/phone/check", ApiJson.encodeToString(PhoneCheckIn(phone, code))))
    suspend fun linkCode(code: String): Note =
        ApiJson.decodeFromString(webSend("POST", "/profile/link-code", ApiJson.encodeToString(CodeIn(code.trim()))))

    // --- checkout ---
    suspend fun deliveryConfig(): DeliveryConfig = webGet("/delivery/config")
    suspend fun cities(q: String): DirectoryResult = webGet("/delivery/cities?q=" + URLEncoder.encode(q, "UTF-8"))
    suspend fun warehouses(cityRef: String, settlementRef: String, q: String): DirectoryResult =
        webGet("/delivery/warehouses?city_ref=" + URLEncoder.encode(cityRef, "UTF-8") + "&settlement_ref=" +
            URLEncoder.encode(settlementRef, "UTF-8") + "&q=" + URLEncoder.encode(q, "UTF-8"))
    suspend fun checkoutDefaults(): CheckoutDefaults = webGet("/checkout/defaults")
    suspend fun quote(request: QuoteRequest): Quote = webSend("POST", "/checkout/quote", request)
    suspend fun checkout(payload: CheckoutPayload): CheckoutResult = webSend("POST", "/checkout", payload)
    suspend fun checkoutStatus(key: String): CheckoutResult = webGet("/checkout/status?checkout_key=" + URLEncoder.encode(key, "UTF-8"))

    // --- blog ---
    suspend fun myComments(postId: Int): List<Comment> = webGet("/blog/posts/$postId/mine")
    suspend fun comment(postId: Int, body: String, parentId: Int?, clientKey: String) {
        webSend("POST", "/blog/posts/$postId/comments", ApiJson.encodeToString(CommentIn(body, parentId, clientKey)))
    }
    suspend fun editComment(id: Int, body: String, version: Int) {
        webSend("PUT", "/blog/comments/$id", ApiJson.encodeToString(CommentEditIn(body, version)))
    }
    suspend fun deleteComment(id: Int, version: Int) {
        webSend("DELETE", "/blog/comments/$id", ApiJson.encodeToString(VersionIn(version)))
    }

    /** Anonymous first-party visit (no personal data), once per launch; retried on failure. */
    suspend fun recordVisit() {
        if (visitSent) return
        runCatching {
            api.raw("POST", "/api/web/analytics/visit", ApiJson.encodeToString(VisitIn(visitId, Attribution())))
            visitSent = true
        }
    }
}
