package ua.accordniche.shop.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.ShopViewModel
import ua.accordniche.shop.data.Aroma
import ua.accordniche.shop.data.Storefront
import ua.accordniche.shop.data.money
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.Eyebrow
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.ImageTile
import ua.accordniche.shop.ui.components.OutlineButton
import ua.accordniche.shop.ui.components.PrimaryButton
import ua.accordniche.shop.ui.components.ProductShelf
import ua.accordniche.shop.ui.components.RequestContent
import ua.accordniche.shop.ui.components.SectionHeading
import ua.accordniche.shop.ui.components.StateBlock
import ua.accordniche.shop.ui.components.TextLink
import ua.accordniche.shop.ui.components.rememberRequest
import ua.accordniche.shop.ui.info.HowItWorksBand
import ua.accordniche.shop.ui.info.InfoDialog
import ua.accordniche.shop.ui.info.ShopFooter
import ua.accordniche.shop.ui.theme.Accord

fun volumesOf(items: List<Aroma>): List<Int> = items.flatMap { it.volumes }.filter { it > 0 }.distinct().sorted()

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(app: AppContainer, nav: Nav, shop: ShopViewModel) {
    val request = rememberRequest<Storefront>("storefront") { app.store.storefront() }
    val site by shop.site.collectAsStateWithLifecycle()
    var info by rememberSaveable { mutableStateOf("") }
    val scroll = TopAppBarDefaults.enterAlwaysScrollBehavior()
    Scaffold(Modifier.nestedScroll(scroll.nestedScrollConnection), topBar = {
        AccordTopBar(scroll = scroll, actions = {
            IconButton(onClick = { nav.tab(Routes.catalog()) }) { Icon(Icons.Outlined.Search, "Пошук") }
        })
    }) { padding ->
        PullToRefreshBox(isRefreshing = request.loading && request.data != null, onRefresh = { request.retry(); shop.validate() },
            modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(Modifier.fillMaxSize()) {
                val data = request.data
                item { Hero(nav, data?.selection?.firstOrNull(), volumesOf(data?.selection.orEmpty())) }
                item {
                    RequestContent(request, loadingText = "Завантажуємо товари…") { front ->
                        if (front.total == 0) StateBlock("Поки немає товарів", "Перегляньте інші добірки або завітайте пізніше.")
                    }
                }
                if (data != null) {
                    item {
                        if (data.hits.isNotEmpty()) ProductShelf("Хіти розпиву", data.hits, { nav.go(Routes.product(it)) },
                            "Найпопулярніші за підтвердженими продажами за ${data.windowDays} днів.") { nav.go(Routes.catalog(kind = "hits")) }
                        else ProductShelf("Оберіть свій аромат", data.selection, { nav.go(Routes.product(it)) }, "Товари з актуального каталогу магазину.") { nav.tab(Routes.catalog()) }
                    }
                    if (data.total > 0) item { BuyerFacts(volumesOf(data.selection)) { nav.go(Routes.HOW) } }
                    item { ProductShelf("Новинки", data.newArrivals, { nav.go(Routes.product(it)) }) { nav.go(Routes.catalog(kind = "new")) } }
                    item { ProductShelf("Рекомендуємо", data.recommended, { nav.go(Routes.product(it)) }, "Добірка магазину для знайомства з ароматами.") { nav.go(Routes.catalog(kind = "recommended")) } }
                    item { QuickLinks(nav) }
                }
                item { HowItWorksBand() }
                item { ShopFooter(nav, site) { info = it } }
            }
        }
    }
    if (info.isNotEmpty()) InfoDialog(info, site) { info = "" }
}

@Composable
private fun Hero(nav: Nav, item: Aroma?, volumes: List<Int>) {
    Column(Modifier.fillMaxWidth().padding(horizontal = Gutter).padding(top = 18.dp, bottom = 10.dp)) {
        Eyebrow("Нішева парфумерія у вашому форматі")
        Spacer(Modifier.height(16.dp))
        Text("Знайдіть аромат,\nякий стане\nвашим", style = MaterialTheme.typography.displayMedium, modifier = Modifier.semantics { heading() })
        Spacer(Modifier.height(16.dp))
        Text("Обирайте аромат і зручний об’єм. Знайомтеся з парфумерією у власному ритмі — перед рішенням про повний флакон.",
            style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
        if (volumes.isNotEmpty()) Text("Об’єми ${volumes.joinToString(" / ")} мл · ціна за мілілітр біля кожного аромату",
            style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle, modifier = Modifier.padding(top = 10.dp))
        Spacer(Modifier.height(20.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PrimaryButton("Обрати аромат", { nav.tab(Routes.catalog()) })
            TextLink("Новинки →", { nav.go(Routes.catalog(kind = "new")) })
        }
        if (item != null && item.image.isNotBlank()) {
            Spacer(Modifier.height(22.dp))
            Column(Modifier.clickable { nav.go(Routes.product(item.defaultProductId)) }) {
                ImageTile(item.image, listOf(item.brand, item.name).joinToString(" "), ratio = 1.25f)
                Row(Modifier.fillMaxWidth().background(Accord.colors.linen).padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(listOf(item.brand, item.name).filter { it.isNotBlank() }.joinToString(" · "), style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    Text("від " + money(item.minPrice), style = MaterialTheme.typography.bodySmall, color = Accord.colors.accent)
                }
            }
        }
    }
}

/** Answers to «what is in the vial, what does it cost, when is it sent, what if something is wrong». */
@Composable
private fun BuyerFacts(volumes: List<Int>, onHow: () -> Unit) {
    val facts = listOf(
        "Формат" to if (volumes.isNotEmpty()) "Розпив в об’ємах ${volumes.joinToString(" / ")} мл: спробуйте аромат, перш ніж купувати флакон." else "Розпив у невеликих об’ємах: спробуйте аромат, перш ніж купувати флакон.",
        "Чесна ціна" to "Біля кожного аромату — ціна за мілілітр, тож об’єми легко порівняти. Підсумок із доставкою видно до підтвердження.",
        "Доставка" to "Новою поштою. Статус замовлення й номер ТТН — в історії покупок особистого кабінету.",
        "Якщо щось не так" to "До відправлення замовлення можна скасувати в кабінеті. З питаннями щодо отриманого товару — контакти внизу сторінки.",
    )
    Column(Modifier.fillMaxWidth().padding(horizontal = Gutter, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionHeading("Перед замовленням")
        facts.forEach { (title, text) ->
            Column(Modifier.fillMaxWidth().background(Accord.colors.soft).border(1.dp, Accord.colors.line).padding(16.dp)) {
                Text(title, style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                Spacer(Modifier.height(6.dp))
                Text(text, style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSecondary)
            }
        }
        TextLink("ЯК ЦЕ ПРАЦЮЄ →", onHow)
    }
}

@Composable
private fun QuickLinks(nav: Nav) {
    Row(Modifier.fillMaxWidth().padding(horizontal = Gutter, vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlineButton("Набори", { nav.go("sets") }, Modifier.weight(1f))
        OutlineButton("Бренди", { nav.go(Routes.BRANDS) }, Modifier.weight(1f))
    }
}
