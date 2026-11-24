package ua.accordniche.shop

import android.app.Application
import android.content.Context
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.disk.DiskCache
import coil3.memory.MemoryCache
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import coil3.request.crossfade
import okio.Path.Companion.toOkioPath
import okhttp3.OkHttpClient
import ua.accordniche.shop.data.AccountRepository
import ua.accordniche.shop.data.ApiClient
import ua.accordniche.shop.data.CartStore
import ua.accordniche.shop.data.CheckoutAttemptStore
import ua.accordniche.shop.data.PersistentCookieJar
import ua.accordniche.shop.data.StoreRepository
import java.util.concurrent.TimeUnit

/** Manual dependency container: one HTTP client, cookie jar and repositories per process. */
class AppContainer(context: Context) {
    val baseUrl: String = BuildConfig.BASE_URL.trimEnd('/')
    val host: String = baseUrl.substringAfter("://").substringBefore('/').substringBefore(':')
    private val cookies = PersistentCookieJar(context.getSharedPreferences("accord_cookies", Context.MODE_PRIVATE), host)
    val http: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(cookies)
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            chain.proceed(chain.request().newBuilder()
                .header("User-Agent", "AccordNicheAndroid/${BuildConfig.VERSION_NAME} (Android ${android.os.Build.VERSION.RELEASE})")
                .build())
        }
        .build()
    val api = ApiClient(baseUrl, http)
    val store = StoreRepository(api)
    val account = AccountRepository(api) { cookies.clear() }
    val cartStore = CartStore(context)
    val attempts = CheckoutAttemptStore(context)
}

class AccordApp : Application(), SingletonImageLoader.Factory {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }

    // Product photos: shared HTTP client (same host), memory + disk cache.
    override fun newImageLoader(context: PlatformContext): ImageLoader = ImageLoader.Builder(context)
        .components { add(OkHttpNetworkFetcherFactory(callFactory = { container.http })) }
        .memoryCache { MemoryCache.Builder().maxSizePercent(context, 0.2).build() }
        .diskCache { DiskCache.Builder().directory(cacheDir.resolve("images").toOkioPath()).maxSizeBytes(80L * 1024 * 1024).build() }
        .crossfade(true)
        .build()
}

val Context.container: AppContainer get() = (applicationContext as AccordApp).container
