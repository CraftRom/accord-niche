package ua.accordniche.shop.ui.product

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.ShopViewModel
import ua.accordniche.shop.data.AromaDetail
import ua.accordniche.shop.data.genderName
import ua.accordniche.shop.data.money
import ua.accordniche.shop.data.perMl
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.Eyebrow
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.ImageTile
import ua.accordniche.shop.ui.components.PrimaryButton
import ua.accordniche.shop.ui.components.ProductShelf
import ua.accordniche.shop.ui.components.RequestContent
import ua.accordniche.shop.ui.components.rememberRequest
import ua.accordniche.shop.ui.theme.Accord

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProductScreen(app: AppContainer, nav: Nav, shop: ShopViewModel, id: Int) {
    val request = rememberRequest<AromaDetail>("aroma:$id") { app.store.aroma(id) }
    var sku by rememberSaveable { mutableIntStateOf(id) }
    val cartState by shop.cart.collectAsStateWithLifecycle()
    val group = request.data?.item
    Scaffold(topBar = {
        AccordTopBar(group?.let { listOf(it.brand, it.name).filter(String::isNotBlank).joinToString(" ") } ?: "Аромат", onBack = nav::back, actions = {
            if (group != null) IconButton(onClick = {
                nav.share(listOf(group.brand, group.name).filter(String::isNotBlank).joinToString(" ") + " — ACCORD NICHE\n" + app.baseUrl + "/aroma/" + sku)
            }) { Icon(Icons.Outlined.Share, "Поділитися") }
        })
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())) {
            RequestContent(request, notFound = "Товар недоступний", loadingText = "Завантажуємо аромат…") { detail ->
                val item = detail.item
                val current = item.variants.find { it.id == sku } ?: item.variants.find { it.id == id } ?: item.variants.firstOrNull()
                if (current == null) return@RequestContent
                ImageTile(current.image ?: item.image, listOf(item.brand, item.name).joinToString(" "), ratio = 1f / 1.04f)
                Column(Modifier.padding(horizontal = Gutter, vertical = 20.dp)) {
                    if (item.brand.isNotBlank()) Eyebrow(item.brand)
                    Text(item.name, style = MaterialTheme.typography.displaySmall, modifier = Modifier.padding(vertical = 8.dp).semantics { heading() })
                    Text(genderName[item.gender] ?: "унісекс", style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSubtle)
                    if (item.isHit) Text("Хіт продажів · за останні 90 днів", style = MaterialTheme.typography.bodySmall,
                        color = Accord.colors.accent, modifier = Modifier.padding(top = 8.dp))
                    if (item.description.isNotBlank()) Text(item.description, style = MaterialTheme.typography.bodyLarge,
                        color = Accord.colors.textSecondary, modifier = Modifier.padding(top = 18.dp))

                    HorizontalDivider(Modifier.padding(vertical = 22.dp), color = Accord.colors.line)
                    Text("Оберіть об’єм", style = MaterialTheme.typography.titleSmall)
                    Spacer(Modifier.height(12.dp))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        item.variants.forEach { variant ->
                            val chosen = variant.id == current.id
                            OutlinedButton(onClick = { sku = variant.id }, shape = MaterialTheme.shapes.small,
                                modifier = Modifier.widthIn(min = 84.dp).heightIn(min = 52.dp).semantics { selected = chosen },
                                border = BorderStroke(1.dp, if (chosen) Accord.colors.ink else MaterialTheme.colorScheme.outline),
                                colors = androidx.compose.material3.ButtonDefaults.outlinedButtonColors(
                                    containerColor = if (chosen) Accord.colors.ink else Accord.colors.surface,
                                    contentColor = if (chosen) Accord.colors.surface else Accord.colors.ink)) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(variant.volumeMl?.let { "$it мл" } ?: variant.name, style = MaterialTheme.typography.bodySmall)
                                    Text(if (variant.stock > 0) money(variant.price) else "Немає", style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }
                    }

                    HorizontalDivider(Modifier.padding(vertical = 22.dp), color = Accord.colors.line)
                    Text(current.volumeMl?.let { "ЦІНА ЗА $it МЛ" } ?: "ЦІНА", style = MaterialTheme.typography.labelMedium, color = Accord.colors.accent)
                    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 6.dp)) {
                        Text(money(current.price), style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Medium))
                        if (current.isSale && current.oldPrice != null) Text(money(current.oldPrice), style = MaterialTheme.typography.bodyMedium.copy(textDecoration = TextDecoration.LineThrough),
                            color = Accord.colors.textSubtle)
                    }
                    current.volumeMl?.takeIf { it > 0 }?.let { Text("${money(perMl(current.price, it))} / мл", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle) }
                    Text(if (current.stock > 0) "У наявності" else "Немає в наявності", style = MaterialTheme.typography.bodySmall,
                        color = if (current.stock > 0) Accord.colors.success else Accord.colors.textSubtle, modifier = Modifier.padding(top = 4.dp))
                    Spacer(Modifier.height(18.dp))
                    val inCart = cartState.cart[current.id] ?: 0
                    PrimaryButton(if (current.stock > 0) "Додати в кошик" else "Немає в наявності", {
                        if (shop.add(current.copy(brand = item.brand))) shop.notify("Додано в кошик: ${item.name}" + (current.volumeMl?.let { ", $it мл" } ?: ""))
                    }, Modifier.fillMaxWidth(), enabled = current.stock > 0 && inCart < minOf(current.stock, 99))
                    if (inCart > 0) androidx.compose.material3.TextButton(onClick = { nav.tab(Routes.CART) }, modifier = Modifier.fillMaxWidth()) {
                        Text("У кошику: $inCart шт. Перейти до кошика →", color = Accord.colors.accent)
                    }
                    Text("Ціна й наявність перевіряються повторно під час оформлення.", style = MaterialTheme.typography.bodySmall,
                        color = Accord.colors.textSubtle, modifier = Modifier.padding(top = 10.dp))
                }
                Column(Modifier.background(Accord.colors.surface)) {
                    ProductShelf("Схожі аромати", detail.related, { nav.go(Routes.product(it)) })
                }
            }
        }
    }
}
