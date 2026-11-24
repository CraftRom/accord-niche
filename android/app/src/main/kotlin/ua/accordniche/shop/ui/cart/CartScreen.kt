package ua.accordniche.shop.ui.cart

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ua.accordniche.shop.ShopViewModel
import ua.accordniche.shop.data.money
import ua.accordniche.shop.data.telegramCheckoutUrl
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.ImageTile
import ua.accordniche.shop.ui.components.InlineMessage
import ua.accordniche.shop.ui.components.OutlineButton
import ua.accordniche.shop.ui.components.PrimaryButton
import ua.accordniche.shop.ui.components.QtyControl
import ua.accordniche.shop.ui.components.StateBlock
import ua.accordniche.shop.ui.components.TextLink
import ua.accordniche.shop.ui.theme.Accord

@Composable
fun CartScreen(nav: Nav, shop: ShopViewModel) {
    val state by shop.cart.collectAsStateWithLifecycle()
    val site by shop.site.collectAsStateWithLifecycle()
    // Every visit re-checks prices and stock, like opening the basket on the site.
    LaunchedEffect(Unit) { shop.validate() }
    Scaffold(topBar = { AccordTopBar("Кошик") }, bottomBar = {
        if (state.lines.isNotEmpty()) Surface(tonalElevation = 0.dp, color = Accord.colors.surface) {
            Column(Modifier.fillMaxWidth().padding(Gutter)) {
                HorizontalDivider(color = Accord.colors.line)
                Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Сума за товари", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                    Text(money(state.total), style = MaterialTheme.typography.headlineSmall)
                }
                PrimaryButton("Оформити замовлення →", { nav.go(Routes.CHECKOUT) }, Modifier.fillMaxWidth(), enabled = !state.blocked)
                val link = telegramCheckoutUrl(site.miniappUrl, state.cart, state.products)
                if (!state.blocked && link.isNotEmpty()) TextLink("Продовжити в Telegram Mini App", { nav.open(link) }, Modifier.fillMaxWidth())
                Text("Доставка не входить у суму: її оплачують перевізнику за його тарифами. Знижки, бонуси й остаточну суму покаже оформлення. Кошик зберігається на цьому пристрої.",
                    style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle, modifier = Modifier.padding(top = 6.dp))
            }
        }
    }) { padding ->
        PullToRefreshBox(isRefreshing = state.loading && state.lines.isNotEmpty(), onRefresh = shop::validate, modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = Gutter, vertical = 12.dp)) {
                if (state.cart.isNotEmpty() && state.error.isNotEmpty()) item {
                    StateBlock("Не вдалося перевірити кошик", state.error, error = true, action = { OutlineButton("Спробувати ще раз", shop::validate) })
                }
                if (state.loading) item { InlineMessage("Перевіряємо ціни й наявність…") }
                items(state.unresolved, key = { "u$it" }) { id ->
                    if (!state.loading) Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Товар потребує перевірки наявності.", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                        TextLink("Прибрати з кошика", { shop.change(id, 0) }, danger = true)
                    }
                }
                items(state.lines, key = { it.first.id }) { (product, qty) ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 14.dp)) {
                        Column(Modifier.width(92.dp)) { ImageTile(product.image, product.name, ratio = 0.85f) }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text((if (product.brand.isNotBlank()) product.brand + " · " else "") + product.name, style = MaterialTheme.typography.titleSmall)
                            Text(listOfNotNull(product.volumeMl?.let { "$it мл" }, money(product.price) + " за шт.").joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                            Text((if (qty > 1) "$qty × ${money(product.price)} = " else "") + money(product.price * qty.toBigDecimal()),
                                style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                            state.lineNotes[product.id]?.let { InlineMessage(it) }
                            QtyControl(qty, { shop.change(product.id, it) }, product.stock, product.name) { shop.change(product.id, 0) }
                            if (qty >= product.stock && product.stock < 99) Text("У наявності ${product.stock} шт. — це максимум.",
                                style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                        }
                    }
                    HorizontalDivider(color = Accord.colors.line)
                }
                if (state.cart.isEmpty() && state.restored) item {
                    Column(Modifier.fillMaxWidth().padding(vertical = 48.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("У кошику поки порожньо", style = MaterialTheme.typography.titleLarge)
                        Spacer(Modifier.height(20.dp))
                        OutlineButton("Переглянути аромати", { nav.tab(Routes.catalog()) })
                    }
                }
            }
        }
    }
}
