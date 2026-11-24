package ua.accordniche.shop.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.LocalDrink
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import ua.accordniche.shop.container
import ua.accordniche.shop.data.Aroma
import ua.accordniche.shop.data.genderName
import ua.accordniche.shop.data.money
import ua.accordniche.shop.ui.theme.Accord

/** Bottles are never cropped: contain on the linen backdrop, fixed ratio before load. */
@Composable
fun ImageTile(source: String?, description: String, modifier: Modifier = Modifier, ratio: Float = 1f) {
    val url = LocalContext.current.container.api.absolute(source)
    var failed by remember(url) { mutableStateOf(false) }
    Box(modifier.fillMaxWidth().aspectRatio(ratio).background(Accord.colors.linen), contentAlignment = Alignment.Center) {
        if (url != null && !failed) {
            AsyncImage(model = url, contentDescription = description, contentScale = ContentScale.Fit,
                modifier = Modifier.fillMaxSize().padding(10.dp), onError = { failed = true })
        } else {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Outlined.LocalDrink, null, tint = Accord.colors.textSubtle, modifier = Modifier.size(36.dp))
                Spacer(Modifier.height(6.dp))
                Text("Зображення недоступне", style = MaterialTheme.typography.labelSmall, color = Accord.colors.textSubtle)
            }
        }
    }
}

@Composable
fun Badge(text: String, dark: Boolean = false) {
    Text(text, modifier = Modifier.background(if (dark) Accord.colors.ink else Accord.colors.surface).padding(horizontal = 7.dp, vertical = 3.dp),
        style = MaterialTheme.typography.labelSmall, color = if (dark) Accord.colors.surface else Accord.colors.ink)
}

@Composable
fun ProductCard(item: Aroma, onOpen: (Int) -> Unit, modifier: Modifier = Modifier) {
    val label = listOf(item.brand, item.name).filter { it.isNotBlank() }.joinToString(" ")
    Column(modifier.border(1.dp, Accord.colors.line).background(Accord.colors.surface)
        .clickable(role = Role.Button, onClickLabel = "Переглянути") { onOpen(item.defaultProductId) }
        .semantics(mergeDescendants = true) { contentDescription = "$label, від ${money(item.minPrice)}" }) {
        Box {
            ImageTile(item.image, label, ratio = 1f)
            Row(Modifier.padding(8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                if (item.stock <= 0) Badge("Немає в наявності")
                else {
                    if (item.isHit) Badge("Хіт продажів", dark = true)
                    if (item.isNew) Badge("Новинка")
                }
            }
        }
        Column(Modifier.padding(12.dp)) {
            if (item.brand.isNotBlank()) Text(item.brand.uppercase(), style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold),
                color = Accord.colors.accent, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            Text(item.name, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis, minLines = 2)
            Spacer(Modifier.height(4.dp))
            Text((genderName[item.gender] ?: "унісекс") + if (item.volumes.isNotEmpty()) " · " + item.volumes.joinToString(" / ") + " мл" else "",
                style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(10.dp))
            Text("від " + money(item.minPrice), style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
            item.pricePerMl?.let { Text("від ${money(it)} / мл", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle) }
            Spacer(Modifier.height(6.dp))
            Text(if (item.stock > 0) "У наявності" else "Тимчасово відсутній", style = MaterialTheme.typography.labelSmall,
                color = if (item.stock > 0) Accord.colors.success else Accord.colors.textSubtle)
        }
    }
}

/** Home and product page shelf: heading, «see all» and a swipeable row of cards. */
@Composable
fun ProductShelf(title: String, items: List<Aroma>, onOpen: (Int) -> Unit, description: String? = null, onSeeAll: (() -> Unit)? = null) {
    if (items.isEmpty()) return
    Column(Modifier.fillMaxWidth().padding(vertical = 22.dp)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = Gutter), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                SectionHeading(title)
                if (description != null) Text(description, style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSecondary,
                    modifier = Modifier.padding(top = 6.dp))
            }
            if (onSeeAll != null) TextLink("ВСІ →", onSeeAll)
        }
        Spacer(Modifier.height(14.dp))
        LazyRow(contentPadding = PaddingValues(horizontal = Gutter), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            items(items, key = { it.key }) { ProductCard(it, onOpen, Modifier.width(176.dp)) }
        }
    }
}
