package ua.accordniche.shop.data

import android.content.SharedPreferences
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl

/**
 * Keeps the shop's session and CSRF cookies across launches, like a browser
 * profile. Only cookies of the shop host are accepted; expired ones are dropped.
 */
class PersistentCookieJar(private val prefs: SharedPreferences, private val host: String) : CookieJar {
    private val cookies = mutableMapOf<String, Cookie>()

    init {
        val now = System.currentTimeMillis()
        prefs.all.forEach { (key, value) ->
            val cookie = (value as? String)?.let { Cookie.parse(HttpUrl.Builder().scheme("https").host(host).build(), it) }
            if (cookie != null && cookie.expiresAt > now) cookies[key] = cookie
        }
    }

    private fun keyOf(cookie: Cookie) = cookie.name + "|" + cookie.path

    @Synchronized
    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        if (url.host != host) return
        val editor = prefs.edit()
        val now = System.currentTimeMillis()
        for (cookie in cookies) {
            val key = keyOf(cookie)
            if (cookie.expiresAt <= now) {
                this.cookies.remove(key); editor.remove(key)
            } else {
                this.cookies[key] = cookie
                // Session cookies (no max-age) still live only in memory.
                if (cookie.persistent) editor.putString(key, cookie.toString()) else editor.remove(key)
            }
        }
        editor.apply()
    }

    @Synchronized
    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        if (url.host != host) return emptyList()
        val now = System.currentTimeMillis()
        cookies.entries.removeAll { it.value.expiresAt <= now }
        return cookies.values.filter { it.matches(url) }
    }

    @Synchronized
    fun clear() {
        cookies.clear()
        prefs.edit().clear().apply()
    }
}
