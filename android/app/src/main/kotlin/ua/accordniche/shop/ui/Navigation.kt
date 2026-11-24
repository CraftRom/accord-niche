package ua.accordniche.shop.ui

import android.content.Intent
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Article
import androidx.compose.material.icons.outlined.GridView
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.ShoppingBag
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.navigation.navDeepLink
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.ShopViewModel
import ua.accordniche.shop.ui.blog.BlogArticleScreen
import ua.accordniche.shop.ui.blog.BlogListScreen
import ua.accordniche.shop.ui.cart.CartScreen
import ua.accordniche.shop.ui.catalog.BrandsScreen
import ua.accordniche.shop.ui.catalog.CatalogScreen
import ua.accordniche.shop.ui.checkout.CheckoutScreen
import ua.accordniche.shop.ui.checkout.SuccessScreen
import ua.accordniche.shop.ui.home.HomeScreen
import ua.accordniche.shop.ui.info.HowItWorksScreen
import ua.accordniche.shop.ui.info.LegalScreen
import ua.accordniche.shop.ui.product.ProductScreen
import ua.accordniche.shop.ui.profile.ProfileScreen
import ua.accordniche.shop.ui.theme.Accord
import java.net.URLEncoder

object Routes {
    const val HOME = "home"
    const val CATALOG = "catalog?kind={kind}&brand={brand}&q={q}"
    const val BRANDS = "brands"
    const val PRODUCT = "aroma/{id}"
    const val CART = "cart"
    const val CHECKOUT = "checkout"
    const val SUCCESS = "success"
    const val PROFILE = "profile"
    const val BLOG = "blog?q={q}"
    const val ARTICLE = "blog/{slug}"
    const val LEGAL = "legal/{key}"
    const val HOW = "how"

    private fun e(value: String) = URLEncoder.encode(value, "UTF-8")
    fun catalog(kind: String = "", brand: String = "", q: String = "") = "catalog?kind=${e(kind)}&brand=${e(brand)}&q=${e(q)}"
    fun product(id: Int) = "aroma/$id"
    fun article(slug: String) = "blog/${e(slug)}"
    fun legal(key: String) = "legal/$key"
}

/** Everything a screen needs to move around and talk to the shop. */
class Nav(val controller: NavHostController, private val context: android.content.Context) {
    fun go(route: String) = controller.navigate(route) { launchSingleTop = true }
    fun back() { if (!controller.popBackStack()) go(Routes.HOME) }
    fun tab(route: String) = controller.navigate(route) {
        popUpTo(controller.graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
    /** External pages (Nova Poshta, documents, Telegram) in a Custom Tab or their own app. */
    fun open(url: String) {
        val uri = Uri.parse(url)
        if (uri.host == "t.me" || uri.scheme == "tel" || uri.scheme == "mailto") {
            runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            return
        }
        runCatching { CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, uri) }
            .onFailure { runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } }
    }
    fun share(text: String) {
        val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text)
        context.startActivity(Intent.createChooser(send, "Поділитися").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}

private data class Tab(val route: String, val base: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab(Routes.HOME, "home", "Головна", Icons.Outlined.Home),
    Tab(Routes.catalog(), "catalog", "Каталог", Icons.Outlined.GridView),
    Tab("blog?q=", "blog?", "Блог", Icons.AutoMirrored.Outlined.Article),
    Tab(Routes.CART, "cart", "Кошик", Icons.Outlined.ShoppingBag),
    Tab(Routes.PROFILE, "profile", "Профіль", Icons.Outlined.Person),
)

@Composable
fun AccordRoot(app: AppContainer, newIntent: Intent? = null) {
    val controller = rememberNavController()
    val context = LocalContext.current
    val nav = remember(controller) { Nav(controller, context) }
    val shop: ShopViewModel = viewModel(factory = viewModelFactory { initializer { ShopViewModel(app) } })
    val cart by shop.cart.collectAsStateWithLifecycle()
    val notice by shop.notice.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val entry by controller.currentBackStackEntryAsState()
    val current = entry?.destination?.route.orEmpty()
    val base = app.baseUrl

    // A site link opened while the app was already running.
    LaunchedEffect(newIntent) { newIntent?.let { controller.handleDeepLink(it) } }

    LaunchedEffect(notice) {
        if (notice.isNotBlank()) {
            val result = snackbar.showSnackbar(notice, actionLabel = "Закрити", duration = SnackbarDuration.Long)
            if (result == SnackbarResult.ActionPerformed || result == SnackbarResult.Dismissed) shop.dismissNotice()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            Column {
                HorizontalDivider(color = Accord.colors.line)
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface, tonalElevation = androidx.compose.ui.unit.Dp(0f)) {
                    tabs.forEach { tab ->
                        val selected = when (tab.base) {
                            "home" -> current == Routes.HOME
                            "catalog" -> current.startsWith("catalog") || current.startsWith("aroma") || current == Routes.BRANDS || current == "sets"
                            "blog?" -> current.startsWith("blog")
                            "cart" -> current == Routes.CART || current == Routes.CHECKOUT || current == Routes.SUCCESS
                            else -> current == Routes.PROFILE
                        }
                        NavigationBarItem(
                            selected = selected,
                            onClick = { nav.tab(tab.route) },
                            icon = {
                                if (tab.base == "cart" && cart.count > 0) BadgedBox(badge = { Badge(containerColor = Accord.colors.ink, contentColor = Accord.colors.surface) { Text("${cart.count}") } }) {
                                    Icon(tab.icon, null)
                                } else Icon(tab.icon, null)
                            },
                            label = { Text(tab.label, style = MaterialTheme.typography.labelSmall) },
                            modifier = Modifier.semantics { if (tab.base == "cart") contentDescription = "Кошик, товарів ${cart.count}" },
                            colors = NavigationBarItemDefaults.colors(indicatorColor = Accord.colors.linen, selectedIconColor = Accord.colors.ink,
                                selectedTextColor = Accord.colors.ink, unselectedIconColor = Accord.colors.textSubtle, unselectedTextColor = Accord.colors.textSubtle),
                        )
                    }
                }
            }
        },
        contentWindowInsets = WindowInsets(0),
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            NavHost(controller, startDestination = Routes.HOME,
                enterTransition = { fadeIn() }, exitTransition = { fadeOut() }) {
                composable(Routes.HOME) { HomeScreen(app, nav, shop) }
                composable(Routes.CATALOG, arguments = listOf(
                    navArgument("kind") { type = NavType.StringType; defaultValue = "" },
                    navArgument("brand") { type = NavType.StringType; defaultValue = "" },
                    navArgument("q") { type = NavType.StringType; defaultValue = "" },
                ), deepLinks = listOf(
                    navDeepLink { uriPattern = "$base/catalog?kind={kind}&brand={brand}&q={q}" },
                    navDeepLink { uriPattern = "$base/catalog" },
                )) { back ->
                    CatalogScreen(app, nav, back.arguments?.getString("kind").orEmpty(), back.arguments?.getString("brand").orEmpty(),
                        back.arguments?.getString("q").orEmpty())
                }
                composable("sets", deepLinks = listOf(navDeepLink { uriPattern = "$base/sets" })) { CatalogScreen(app, nav, "sets", "", "") }
                composable(Routes.BRANDS, deepLinks = listOf(navDeepLink { uriPattern = "$base/brands" })) { BrandsScreen(app, nav) }
                composable(Routes.PRODUCT, arguments = listOf(navArgument("id") { type = NavType.IntType }),
                    deepLinks = listOf(navDeepLink { uriPattern = "$base/aroma/{id}" })) { back ->
                    ProductScreen(app, nav, shop, back.arguments?.getInt("id") ?: 0)
                }
                composable(Routes.CART) { CartScreen(nav, shop) }
                composable(Routes.CHECKOUT) { CheckoutScreen(app, nav, shop) }
                composable(Routes.SUCCESS) { SuccessScreen(nav, shop.lastOrder) }
                composable(Routes.PROFILE, deepLinks = listOf(navDeepLink { uriPattern = "$base/profile" })) { ProfileScreen(app, nav, shop) }
                composable(Routes.BLOG, arguments = listOf(navArgument("q") { type = NavType.StringType; defaultValue = "" }),
                    deepLinks = listOf(navDeepLink { uriPattern = "$base/blog?q={q}" }, navDeepLink { uriPattern = "$base/blog" })) { back ->
                    BlogListScreen(app, nav, back.arguments?.getString("q").orEmpty())
                }
                composable(Routes.ARTICLE, arguments = listOf(navArgument("slug") { type = NavType.StringType }),
                    deepLinks = listOf(navDeepLink { uriPattern = "$base/blog/{slug}" })) { back ->
                    BlogArticleScreen(app, nav, back.arguments?.getString("slug").orEmpty())
                }
                composable(Routes.LEGAL, arguments = listOf(navArgument("key") { type = NavType.StringType })) { back ->
                    LegalScreen(app, nav, back.arguments?.getString("key").orEmpty())
                }
                composable(Routes.HOW) { HowItWorksScreen(nav) }
            }
        }
    }
}
