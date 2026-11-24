package ua.accordniche.shop.data

import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.io.InterruptedIOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** A failed request with the shop's own message (FastAPI `detail`). */
class ApiException(
    message: String,
    val status: Int = 0,
    /** Field name → message, from a 422 validation response. */
    val fields: Map<String, String> = emptyMap(),
    val code: String? = null,
) : Exception(message) {
    val notFound get() = status == 404 || status == 410
    val offline get() = status == 0
}

val ApiJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    encodeDefaults = true
}

/**
 * The website's own API. The app is a first-party client of the same origin:
 * it sends the site's Origin and the double-submit CSRF token exactly like the
 * browser does, so no endpoint needed a separate mobile variant.
 */
class ApiClient(val baseUrl: String, val http: OkHttpClient) {
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    fun absolute(path: String?): String? {
        if (path.isNullOrBlank()) return null
        return when {
            path.startsWith("https://") -> path
            path.startsWith("/") -> baseUrl.trimEnd('/') + path
            else -> null
        }
    }

    suspend fun raw(method: String, path: String, body: String? = null, csrf: String? = null): String {
        val builder = Request.Builder().url(baseUrl.trimEnd('/') + path)
            .header("Accept", "application/json")
            .header("Cache-Control", "no-store")
        if (method != "GET") {
            builder.header("Origin", baseUrl.trimEnd('/'))
            if (csrf != null) builder.header("X-CSRF-Token", csrf)
        }
        val requestBody = when {
            body != null -> body.toRequestBody(jsonType)
            method == "GET" -> null
            else -> "".toRequestBody(jsonType)
        }
        builder.method(method, requestBody)
        val response = try {
            http.newCall(builder.build()).await()
        } catch (error: InterruptedIOException) {
            throw ApiException("Сервер не відповів вчасно. Перевірте з’єднання та повторіть дію.")
        } catch (error: IOException) {
            throw ApiException("Немає зв’язку з магазином. Перевірте інтернет і спробуйте ще раз.")
        }
        return withContext(Dispatchers.IO) {
            response.use {
                val text = it.body?.string().orEmpty()
                if (!it.isSuccessful) throw errorOf(it.code, text)
                text
            }
        }
    }

    suspend inline fun <reified T> get(path: String): T = ApiJson.decodeFromString(raw("GET", path).ifEmpty { "null" })

    suspend inline fun <reified T, reified B> send(method: String, path: String, body: B?, csrf: String?): T {
        val text = raw(method, path, body?.let { ApiJson.encodeToString(it) }, csrf)
        return ApiJson.decodeFromString(text.ifEmpty { "{}" })
    }

    companion object {
        fun errorOf(status: Int, text: String): ApiException {
            val payload = runCatching { ApiJson.parseToJsonElement(text).jsonObject }.getOrNull()
            val detail = payload?.get("detail")
            val code = (payload?.get("code") as? JsonPrimitive)?.contentOrNull
            return when {
                detail is JsonPrimitive -> ApiException(detail.content, status, code = code)
                detail is JsonArray -> {
                    val fields = mutableMapOf<String, String>()
                    val messages = detail.mapNotNull { issue ->
                        val obj = issue as? JsonObject ?: return@mapNotNull null
                        val msg = obj["msg"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null
                        val name = (obj["loc"] as? JsonArray)?.lastOrNull()?.jsonPrimitive?.contentOrNull
                        if (name != null) fields[name] = msg.removePrefix("Value error, ")
                        msg.removePrefix("Value error, ")
                    }
                    ApiException(messages.joinToString("; ").ifEmpty { "Перевірте введені дані." }, status, fields, code)
                }
                status == 404 || status == 410 -> ApiException("Сторінку не знайдено або вона більше недоступна.", status)
                status == 429 -> ApiException("Забагато запитів. Зачекайте кілька секунд і повторіть.", status)
                status >= 500 -> ApiException("Магазин тимчасово недоступний. Спробуйте трохи пізніше.", status)
                else -> ApiException("Не вдалося виконати запит ($status)", status)
            }
        }
    }
}

suspend fun Call.await(): Response = suspendCancellableCoroutine { continuation ->
    enqueue(object : Callback {
        override fun onResponse(call: Call, response: Response) = continuation.resume(response)
        override fun onFailure(call: Call, e: IOException) {
            if (!continuation.isCancelled) continuation.resumeWithException(e)
        }
    })
    continuation.invokeOnCancellation { runCatching { cancel() } }
}
