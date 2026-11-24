package ua.accordniche.shop.ui.info

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.data.LegalDoc
import ua.accordniche.shop.data.SiteConfig
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.Eyebrow
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.Logo
import ua.accordniche.shop.ui.components.MarkdownText
import ua.accordniche.shop.ui.components.OutlineButton
import ua.accordniche.shop.ui.components.PageTitle
import ua.accordniche.shop.ui.components.RequestContent
import ua.accordniche.shop.ui.components.SectionHeading
import ua.accordniche.shop.ui.components.TextLink
import ua.accordniche.shop.ui.components.rememberRequest
import ua.accordniche.shop.ui.theme.Accord

/** Short buyer information: footer dialogs and, unchanged, next to the checkout consent. */
object BuyerInfo {
    val delivery = "Доставка й оплата" to "Оформлюйте замовлення в застосунку й обирайте доступний спосіб доставки та оплати. Підсумкова сума, знижки й умови показані перед підтвердженням. Статус і дані відправлення зберігаються в особистому кабінеті."
    val returns = "Повернення та скасування" to "До відправлення замовлення можна скасувати в особистому кабінеті, якщо для його статусу доступне скасування. Із питаннями щодо отриманого товару звертайтеся до магазину за контактами нижче."
    fun of(name: String) = if (name == "returns") returns else delivery
}

val legalTitles = mapOf("terms" to "Публічна оферта", "privacy" to "Політика конфіденційності")

@Composable
fun InfoDialog(name: String, site: SiteConfig, onClose: () -> Unit) {
    val (title, text) = BuyerInfo.of(name)
    AlertDialog(onDismissRequest = onClose,
        confirmButton = { OutlineButton("Зрозуміло", onClose) },
        title = { Column { Eyebrow("ACCORD NICHE"); Spacer(Modifier.height(8.dp)); Text(title, style = MaterialTheme.typography.headlineSmall) } },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(text, style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
                if (site.phone.isNotBlank()) Text(site.phone, style = MaterialTheme.typography.bodyMedium)
                if (site.email.isNotBlank()) Text(site.email, style = MaterialTheme.typography.bodyMedium)
            }
        })
}

@Composable
fun HowItWorksBand() {
    Column(Modifier.fillMaxWidth().background(Accord.colors.inverse).padding(horizontal = Gutter, vertical = 40.dp)) {
        SectionHeading("Як це працює", light = true)
        Spacer(Modifier.height(20.dp))
        listOf(
            Triple("01", "Обираєте аромат", "Порівнюйте бренди, доступні об’єми та ціни за мілілітр."),
            Triple("02", "Оформлюєте замовлення", "Додайте потрібний об’єм у кошик і оберіть спосіб доставки."),
            Triple("03", "Стежите за доставкою", "Історія замовлень і актуальний статус доступні в особистому кабінеті."),
        ).forEach { (number, title, text) ->
            HorizontalDivider(color = Accord.colors.gold.copy(alpha = 0.6f))
            Column(Modifier.padding(vertical = 14.dp)) {
                Text(number, style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Light), color = Accord.colors.accent)
                Text(title, style = MaterialTheme.typography.titleSmall, color = Accord.colors.onInverse, modifier = Modifier.padding(vertical = 6.dp))
                Text(text, style = MaterialTheme.typography.bodySmall, color = Accord.colors.onInverseMuted)
            }
        }
    }
}

/** The site footer: four groups a buyer scans in seconds. */
@Composable
fun ShopFooter(nav: Nav, site: SiteConfig, onInfo: (String) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Accord.colors.inverse).padding(horizontal = Gutter, vertical = 32.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Logo(color = Accord.colors.onInverse)
        Text(listOfNotNull("accordniche.pp.ua", site.sellerName.ifBlank { null }).joinToString(" · "),
            style = MaterialTheme.typography.bodySmall, color = Accord.colors.onInverseMuted)
        FooterGroup("Покупцям", listOf(
            "Каталог" to { nav.tab(Routes.catalog()) }, "Доставка й оплата" to { onInfo("delivery") },
            "Повернення та скасування" to { onInfo("returns") }, "Як це працює" to { nav.go(Routes.HOW) }))
        FooterGroup("Про магазин", listOf("Бренди" to { nav.go(Routes.BRANDS) }, "Блог" to { nav.tab("blog?q=") },
            "Особистий кабінет" to { nav.tab(Routes.PROFILE) }))
        val support = buildList {
            if (site.phone.isNotBlank()) add(site.phone to { nav.open("tel:" + site.phone.filter { it == '+' || it.isDigit() }) })
            if (site.email.isNotBlank()) add(site.email to { nav.open("mailto:" + site.email) })
            if (site.instagramUrl.isNotBlank()) add("Instagram" to { nav.open(site.instagramUrl) })
            if (site.tiktokUrl.isNotBlank()) add("TikTok" to { nav.open(site.tiktokUrl) })
        }
        if (support.isNotEmpty()) FooterGroup("Підтримка", support)
        FooterGroup("Документи", listOf("Публічна оферта" to { nav.go(Routes.legal("terms")) },
            "Політика конфіденційності" to { nav.go(Routes.legal("privacy")) }))
    }
}

@Composable
private fun FooterGroup(title: String, links: List<Pair<String, () -> Unit>>) {
    Column {
        Text(title, style = MaterialTheme.typography.titleSmall, color = Accord.colors.onInverse)
        Row(Modifier.fillMaxWidth()) {
            Column { links.forEach { (label, action) ->
                androidx.compose.material3.TextButton(onClick = action, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
                    Text(label, style = MaterialTheme.typography.bodySmall, color = Accord.colors.onInverseMuted)
                }
            } }
        }
    }
}

@Composable
fun HowItWorksScreen(nav: Nav) {
    Scaffold(topBar = { AccordTopBar("Як це працює", onBack = nav::back) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())) {
            PageTitle("ПРОСТО І ЗРОЗУМІЛО", "Як це працює")
            HowItWorksBand()
            Column(Modifier.padding(Gutter)) { OutlineButton("До каталогу", { nav.tab(Routes.catalog()) }) }
        }
    }
}

/** Public offer and privacy policy, edited by the shop in the dashboard. */
@Composable
fun LegalScreen(app: AppContainer, nav: Nav, key: String) {
    val request = rememberRequest<LegalDoc>("legal:$key") { app.store.legal(key) }
    val title = legalTitles[key] ?: "Документ"
    Scaffold(topBar = { AccordTopBar(title, onBack = nav::back) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())) {
            PageTitle("ДОКУМЕНТИ", title)
            RequestContent(request, notFound = "Документ не знайдено", loadingText = "Завантажуємо документ…") { doc ->
                Column(Modifier.padding(horizontal = Gutter).padding(bottom = 32.dp)) {
                    MarkdownText(doc.body)
                    Spacer(Modifier.height(20.dp))
                    if (key == "terms") TextLink("Політика конфіденційності →", { nav.go(Routes.legal("privacy")) })
                    else TextLink("Публічна оферта →", { nav.go(Routes.legal("terms")) })
                }
            }
        }
    }
}
