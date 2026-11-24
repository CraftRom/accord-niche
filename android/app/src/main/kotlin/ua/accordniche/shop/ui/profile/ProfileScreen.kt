package ua.accordniche.shop.ui.profile

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import kotlinx.coroutines.launch
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.ShopViewModel
import ua.accordniche.shop.data.Order
import ua.accordniche.shop.data.SessionState
import ua.accordniche.shop.data.formatAmount
import ua.accordniche.shop.data.formatDate
import ua.accordniche.shop.data.trackingUrl
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordField
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.Eyebrow
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.InlineMessage
import ua.accordniche.shop.ui.components.LoadingState
import ua.accordniche.shop.ui.components.OutlineButton
import ua.accordniche.shop.ui.components.Panel
import ua.accordniche.shop.ui.components.PrimaryButton
import ua.accordniche.shop.ui.components.StateBlock
import ua.accordniche.shop.ui.components.StatusChip
import ua.accordniche.shop.ui.components.TextLink
import ua.accordniche.shop.ui.info.InfoDialog
import ua.accordniche.shop.ui.info.ShopFooter
import ua.accordniche.shop.ui.theme.Accord

/** Order status as consecutive stages. Only local statuses map onto them; CRM names are shown as is. */
val STAGES = listOf("Прийнято", "В роботі", "Відправлено", "Отримано")
val STAGE_OF = mapOf("new" to 0, "confirmed" to 0, "accepted" to 1, "paid" to 1, "shipped" to 2, "done" to 3)

@Composable
fun ProfileScreen(app: AppContainer, nav: Nav, shop: ShopViewModel) {
    val vm: ProfileViewModel = viewModel(factory = viewModelFactory { initializer { ProfileViewModel(app) } })
    val ui by vm.ui.collectAsStateWithLifecycle()
    val session by shop.session.collectAsStateWithLifecycle()
    val site by shop.site.collectAsStateWithLifecycle()
    val account = session.account
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var confirmCancel by rememberSaveable { mutableStateOf<Long?>(null) }
    var confirmLogout by rememberSaveable { mutableStateOf(false) }
    var info by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(account.hasSession, account.signedIn, account.telegramLinked, account.accountKey) { vm.refreshOrders() }

    val signIn: () -> Unit = {
        vm.startSignIn()
        scope.launch {
            requestGoogleIdToken(context, session.googleClientId)
                .onSuccess(vm::googleLogin)
                .onFailure { vm.signInFailed(it.message.orEmpty()) }
        }
    }

    Scaffold(topBar = {
        AccordTopBar("Мій профіль", actions = {
            if (account.signedIn) IconButton(onClick = { confirmLogout = true }) { Icon(Icons.AutoMirrored.Outlined.Logout, "Вийти з профілю") }
        })
    }) { padding ->
        PullToRefreshBox(isRefreshing = ui.loading && ui.loaded, onRefresh = { scope.launch { runCatching { app.account.refresh() } }; vm.refreshOrders() },
            modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(Modifier.fillMaxSize()) {
                item { Hero(session, ui, nav) { confirmLogout = true } }
                item {
                    Column(Modifier.padding(horizontal = Gutter), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Історія покупок", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
                            TextLink("Оновити", vm::refreshOrders, enabled = account.hasSession && !ui.loading)
                        }
                        InlineMessage(ui.error, error = true)
                        when {
                            !account.hasSession -> StateBlock("Після першого замовлення історія з’явиться тут.", "Щоб вона зберігалась між пристроями, увійдіть через Google.")
                            ui.loading && !ui.loaded -> LoadingState("Завантаження історії замовлень…")
                            ui.loaded && ui.orders.isEmpty() -> StateBlock("Історія покупок поки порожня.", "Тут з’являться замовлення із застосунку, сайту та, після зв’язування, з Telegram Mini App.")
                        }
                    }
                }
                items(ui.orders, key = { it.id }) { order ->
                    OrderCard(order, ui.cancelling, onCancel = { confirmCancel = order.id }, open = nav::open, context = context)
                }
                if (ui.hasMore && !ui.loading) item {
                    OutlineButton(if (ui.loadingMore) "Завантажуємо…" else "Показати більше замовлень", vm::loadMore,
                        Modifier.fillMaxWidth().padding(horizontal = Gutter), enabled = !ui.loadingMore)
                }
                item {
                    Column(Modifier.padding(Gutter), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        if (!account.signedIn) Panel {
                            CardHead("Мій обліковий запис", "off", "Не підключено")
                            Text("Увійдіть через Google, щоб бачити всі замовлення з будь-якого пристрою. Вхід не потрібен для покупки — можна замовити як гість.",
                                style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
                            if (session.googleClientId.isBlank()) Hint(if (session.ready) "Google-вхід поки не підключено. Замовлення без реєстрації доступне." else "Перевіряємо профіль…")
                            else PrimaryButton(if (ui.signingIn) "Входимо…" else "Продовжити з Google", signIn, Modifier.fillMaxWidth(), busy = ui.signingIn)
                            Hint("Після входу тут з’являться підтвердження телефону й зв’язування покупок із Telegram Mini App.")
                        } else {
                            AccountCard(session, ui.saving) { name, done -> vm.rename(name, done) }
                            PhoneCard(session, ui, vm, nav)
                            TelegramCard(session, ui, vm)
                        }
                    }
                }
                item { ShopFooter(nav, site) { info = it } }
            }
        }
    }

    confirmCancel?.let { id ->
        AlertDialog(onDismissRequest = { confirmCancel = null },
            title = { Text("Скасувати замовлення №$id?") },
            text = { Text("Після скасування потрібно буде оформити нове.") },
            confirmButton = { TextButton(onClick = { confirmCancel = null; vm.cancel(id) }) { Text("Скасувати замовлення", color = Accord.colors.danger) } },
            dismissButton = { TextButton(onClick = { confirmCancel = null }) { Text("Залишити", color = Accord.colors.ink) } })
    }
    if (confirmLogout) AlertDialog(onDismissRequest = { confirmLogout = false },
        title = { Text("Вийти з профілю?") },
        text = { Text("Кошик на цьому пристрої збережеться. Щоб знову бачити історію, увійдіть через Google.") },
        confirmButton = { TextButton(onClick = { confirmLogout = false; shop.logout { vm.refreshOrders() } }) { Text("Вийти", color = Accord.colors.danger) } },
        dismissButton = { TextButton(onClick = { confirmLogout = false }) { Text("Залишитися", color = Accord.colors.ink) } })
    if (info.isNotEmpty()) InfoDialog(info, site) { info = "" }
}

@Composable
private fun Hero(session: SessionState, ui: ProfileUi, nav: Nav, onLogout: () -> Unit) {
    val account = session.account
    val first = account.name.trim().split(Regex("\\s+")).firstOrNull().orEmpty()
    Column(Modifier.fillMaxWidth().background(Accord.colors.linen).padding(Gutter), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Eyebrow("Особистий кабінет")
        Text("Мій профіль", style = MaterialTheme.typography.displaySmall)
        if (account.signedIn) Text("Вітаємо" + (if (first.isNotEmpty()) ", $first" else "") + "! " + account.email.orEmpty(),
            style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
        else Text("Увійдіть, щоб бачити замовлення з будь-якого пристрою. Купувати можна й без входу.",
            style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PrimaryButton("Продовжити покупки", { nav.tab(Routes.catalog()) })
            if (account.signedIn) OutlineButton("Вийти", onLogout)
        }
        val profile = ui.profile
        if (account.signedIn && profile != null) Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Fact("Усього замовлень", "${profile.ordersCount}", Modifier.weight(1f))
            Fact("Бонуси", formatAmount(profile.bonusBalance) + " грн", Modifier.weight(1f))
        }
        profile?.latestDelivery?.takeIf { account.signedIn && it.city.isNotBlank() }?.let {
            Fact("Остання доставка", "${it.city}, ${it.address}", Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun Fact(label: String, value: String, modifier: Modifier) {
    Column(modifier.background(Accord.colors.surface).border(1.dp, Accord.colors.line).padding(12.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
        Text(value, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun Hint(text: String) = Text(text, style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)

@Composable
private fun CardHead(title: String, tone: String, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
        StatusChip(tone, label)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun OrderCard(order: Order, cancelling: Long?, onCancel: () -> Unit, open: (String) -> Unit, context: Context) {
    var expanded by rememberSaveable(order.id) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(horizontal = Gutter, vertical = 6.dp).border(1.dp, Accord.colors.line).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row {
            Column(Modifier.weight(1f)) {
                Text("Замовлення №${order.id}", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                Text(formatDate(order.createdAt), style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
            }
            Text(formatAmount(order.total) + " грн", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
        }
        if (order.status == "cancelled") StatusChip("off", "Скасовано")
        else {
            Text(order.statusLabel ?: order.crmStatusName ?: order.status, style = MaterialTheme.typography.bodyMedium)
            val stage = if (order.statusSource == "local") STAGE_OF[order.status] else null
            if (stage != null) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                STAGES.forEachIndexed { index, name ->
                    Column(Modifier.weight(1f)) {
                        androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().height(3.dp)
                            .background(if (index <= stage) Accord.colors.ink else Accord.colors.line))
                        Text(name, style = MaterialTheme.typography.labelSmall,
                            color = if (index == stage) Accord.colors.ink else Accord.colors.textSubtle, modifier = Modifier.padding(top = 4.dp))
                    }
                }
            }
        }
        order.trackingNumber?.takeIf { it.isNotBlank() }?.let { number ->
            FlowRow(verticalArrangement = Arrangement.Center, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("ТТН: $number", style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.align(Alignment.CenterVertically))
                TextLink("Скопіювати", {
                    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("ТТН", number))
                })
                trackingUrl(number)?.let { url -> TextLink("Відстежити на сайті Нової пошти", { open(url) }) }
            }
        }
        Text((if (expanded) "▾ " else "▸ ") + "Склад замовлення (${order.items.size})", style = MaterialTheme.typography.bodySmall,
            color = Accord.colors.accent, modifier = Modifier.clickable { expanded = !expanded }.padding(vertical = 6.dp))
        if (expanded) {
            order.items.forEach { item ->
                Row(Modifier.fillMaxWidth()) {
                    Text("${item.name} × ${item.qty}", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                    Text(formatAmount(item.price * item.qty.toBigDecimal()) + " грн", style = MaterialTheme.typography.bodySmall)
                }
            }
            order.operatorName?.takeIf { it.isNotBlank() }?.let { Hint("Менеджер: $it") }
        }
        if (order.canCancel) {
            HorizontalDivider(color = Accord.colors.line)
            TextLink(if (cancelling == order.id) "Скасовуємо…" else "Скасувати замовлення", onCancel, enabled = cancelling == null, danger = true)
        }
    }
}

@Composable
private fun AccountCard(session: SessionState, saving: Boolean, rename: (String, () -> Unit) -> Unit) {
    var name by rememberSaveable { mutableStateOf("") }
    Panel {
        CardHead("Мій обліковий запис", "ok", "Google")
        Text(session.account.name.ifBlank { "Покупець" }, style = MaterialTheme.typography.titleMedium)
        session.account.email?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle) }
        AccordField(name, { name = it }, "Змінити ім’я", maxLength = 100, placeholder = "Ваше ім’я")
        OutlineButton(if (saving) "Зберігаємо…" else "Зберегти", { rename(name) { name = "" } }, enabled = name.trim().length >= 2 && !saving)
    }
}

/** Free phone confirmation: Telegram bot (own contact) or, when the shop runs a gateway, an SMS code. */
@Composable
private fun PhoneCard(session: SessionState, ui: ProfileUi, vm: ProfileViewModel, nav: Nav) {
    var phone by rememberSaveable { mutableStateOf(session.account.phone ?: "+380") }
    var code by rememberSaveable { mutableStateOf("") }
    val verified = session.account.phoneVerified
    val available = session.telegramPhone || session.smsEnabled
    Panel {
        if (verified) CardHead("Контакти та підтвердження", "ok", "Підтверджено")
        else if (available) CardHead("Контакти та підтвердження", "warn", "Потрібне підтвердження")
        else CardHead("Контакти та підтвердження", "off", "Недоступно")
        Hint(if (verified) "Номер ${session.account.phone} підтверджено."
            else "Підтвердіть свій номер. Лише підтверджений номер може відкрити історію покупок із Mini App — номер, просто вписаний у форму, її не відкриває.")
        if (!verified && session.telegramPhone) {
            PrimaryButton("Підтвердити через Telegram", { vm.phoneViaTelegram(nav::open) }, Modifier.fillMaxWidth(), enabled = !ui.phoneBusy)
            Hint("Безкоштовно й без коду: бот попросить натиснути «📱 Надіслати номер», і Telegram передасть номер вашого акаунта.")
            if (ui.telegramUrl.isNotEmpty()) {
                InlineMessage("Чекаємо підтвердження в боті…")
                TextLink("Відкрити бота ще раз", { nav.open(ui.telegramUrl) })
            }
        }
        if (!verified && session.smsEnabled) {
            if (session.telegramPhone) Hint("Або кодом із SMS:")
            AccordField(phone, { phone = it }, "Ваш номер", required = true, placeholder = "+380XXXXXXXXX", keyboard = KeyboardType.Phone, maxLength = 32)
            OutlineButton(if (ui.phoneBusy && !ui.codeSent) "Надсилаємо…" else if (ui.codeSent) "Надіслати ще раз" else "Надіслати код",
                { vm.sendCode(phone) }, enabled = !ui.phoneBusy)
            if (ui.codeSent) {
                AccordField(code, { code = it.filter(Char::isDigit) }, "SMS-код", required = true, placeholder = "123456", keyboard = KeyboardType.NumberPassword, maxLength = 8)
                PrimaryButton("Підтвердити", { vm.checkCode(phone, code) { code = "" } }, enabled = !ui.phoneBusy && code.length >= 4)
            }
        }
        if (!verified && !available) Hint("Підтвердження номера тимчасово недоступне. Історія Telegram не відкривається за непідтвердженим номером.")
        InlineMessage(ui.phoneMessage)
    }
}

@Composable
private fun TelegramCard(session: SessionState, ui: ProfileUi, vm: ProfileViewModel) {
    var code by rememberSaveable { mutableStateOf("") }
    Panel {
        if (session.account.telegramLinked) {
            CardHead("Покупки з Telegram", "ok", "Підключено")
            Hint("Замовлення з Telegram Mini App показуються в історії вище разом із замовленнями сайту й застосунку.")
            return@Panel
        }
        CardHead("Покупки з Telegram", "off", "Не підключено")
        Hint("Вхід через Google і зв’язування — різні речі: вхід зберігає ваші замовлення, а зв’язування додає до них історію з Mini App. Якщо раніше купували через Mini App, відкрийте в ньому Профіль → «Створити код звʼязування» і вставте код сюди. Ще простіше — кнопка «Підтвердити через Telegram» у картці контактів.")
        AccordField(code, { code = it.trim() }, "Одноразовий код із Mini App", placeholder = "Код із Telegram", maxLength = 40)
        OutlineButton(if (ui.linkBusy) "Зв’язуємо…" else "Зв’язати", { vm.linkTelegram(code) { code = "" } }, enabled = !ui.linkBusy && code.trim().length >= 18)
        InlineMessage(ui.linkMessage)
    }
}
