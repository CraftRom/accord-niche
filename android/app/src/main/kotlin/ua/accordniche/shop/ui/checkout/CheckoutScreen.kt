package ua.accordniche.shop.ui.checkout

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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import kotlinx.coroutines.launch
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.ShopViewModel
import ua.accordniche.shop.data.DirectoryItem
import ua.accordniche.shop.data.formatAmount
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordField
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.Eyebrow
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.InlineMessage
import ua.accordniche.shop.ui.components.OutlineButton
import ua.accordniche.shop.ui.components.Panel
import ua.accordniche.shop.ui.components.PrimaryButton
import ua.accordniche.shop.ui.components.QtyControl
import ua.accordniche.shop.ui.components.StateBlock
import ua.accordniche.shop.ui.components.TextLink
import ua.accordniche.shop.ui.info.BuyerInfo
import ua.accordniche.shop.ui.theme.Accord

@Composable
fun CheckoutScreen(app: AppContainer, nav: Nav, shop: ShopViewModel) {
    val vm: CheckoutViewModel = viewModel(factory = viewModelFactory { initializer { CheckoutViewModel(app) } })
    val ui by vm.ui.collectAsStateWithLifecycle()
    val cart by shop.cart.collectAsStateWithLifecycle()
    val session by shop.session.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val scroll = rememberScrollState()
    val focus = remember { CheckoutViewModel.FIELDS.associateWith { FocusRequester() } }
    var summaryOpen by rememberSaveable { mutableStateOf(false) }
    var docOpen by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(cart) { vm.onCart(cart) }
    LaunchedEffect(vm) {
        vm.onComplete = { result ->
            shop.lastOrder = result
            shop.clear()
            nav.controller.navigate(Routes.SUCCESS) { popUpTo(Routes.CART) }
        }
    }
    val quote = if (ui.quoteSignature.isNotEmpty()) vm.currentQuote else null
    val attempt = ui.attempt
    val shownLines = attempt?.lines?.map { it.product to it.qty } ?: cart.lines
    val subtotal = shownLines.fold(java.math.BigDecimal.ZERO) { sum, (p, q) -> sum + p.price * q.toBigDecimal() }
    val quoteLines = quote?.items?.associateBy { it.productId }.orEmpty()
    val form = ui.form
    val locked = ui.locked

    Scaffold(topBar = { AccordTopBar("Оформлення", onBack = nav::back) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(scroll).padding(horizontal = Gutter, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Eyebrow("Оформлення покупки")
            Text("Ваше замовлення", style = MaterialTheme.typography.displaySmall)

            if (attempt != null) Panel(soft = true) {
                Text("Перевірка надісланого замовлення", style = MaterialTheme.typography.titleLarge)
                Text("Повторне підтвердження використовує той самий запит і не створює дубль. Дані зафіксовані до отримання результату.",
                    style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSecondary)
                OutlineButton(if (ui.checking) "Перевіряємо…" else "Перевірити результат", vm::recover, enabled = !ui.checking && !ui.submitting)
            }
            if (cart.error.isNotEmpty() && attempt == null) StateBlock(null, "Не вдалося оновити ціни й наявність. Введені дані збережені.", error = true,
                action = { TextLink("Спробувати ще раз", shop::validate) })
            if (cart.loading && attempt == null) InlineMessage("Перевіряємо ціни й наявність…")

            if (shownLines.isEmpty() && attempt == null && !cart.blocked && ui.attemptLoaded) {
                Panel {
                    Text("Кошик порожній", style = MaterialTheme.typography.titleLarge)
                    Text("Оберіть аромат, щоб оформити замовлення.", style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
                    PrimaryButton("До каталогу", { nav.tab(Routes.catalog()) })
                }
                return@Column
            }

            // Summary first on a phone, folded to one line.
            Column(Modifier.fillMaxWidth().background(Accord.colors.soft).border(1.dp, Accord.colors.line).padding(16.dp)) {
                Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).clickable(role = Role.Button) { summaryOpen = !summaryOpen }, verticalAlignment = Alignment.CenterVertically) {
                    Text("${shownLines.sumOf { it.second }} шт. · ${formatAmount(attempt?.total ?: quote?.total ?: subtotal)} грн",
                        style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    Text(if (summaryOpen) "Сховати товари" else "Показати товари", style = MaterialTheme.typography.bodySmall, color = Accord.colors.accent)
                }
                if (summaryOpen) shownLines.forEach { (product, qty) ->
                    HorizontalDivider(color = Accord.colors.line)
                    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text((if (product.brand.isNotBlank()) product.brand + " · " else "") + product.name, style = MaterialTheme.typography.bodyMedium)
                            Text((product.volumeMl?.let { "$it мл · " } ?: "") + "$qty шт.", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                            if (attempt == null) QtyControl(qty, { shop.change(product.id, it) }, product.stock, product.name) { shop.change(product.id, 0) }
                        }
                        Text(formatAmount(quoteLines[product.id]?.lineTotal ?: (product.price * qty.toBigDecimal())) + " грн", style = MaterialTheme.typography.bodyMedium)
                    }
                }
                HorizontalDivider(Modifier.padding(vertical = 8.dp), color = Accord.colors.line)
                SummaryRow("Товари", formatAmount(quote?.subtotal ?: subtotal) + " грн")
                if (quote != null) {
                    SummaryRow("Знижка", "−" + formatAmount(quote.discount) + " грн")
                    SummaryRow("Бонуси", "−" + formatAmount(quote.bonusUsed) + " грн")
                }
                SummaryRow(if (attempt != null || quote != null) "За товари" else "Попередня сума", formatAmount(attempt?.total ?: quote?.total ?: subtotal) + " грн", final = true)
                Text("Доставка та послуга післяплати оплачуються окремо за тарифами перевізника. Сума за товари розраховується сервером.",
                    style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle, modifier = Modifier.padding(top = 8.dp))
                if (ui.quoting) InlineMessage("Оновлюємо підсумок…")
            }

            Panel {
                Step("01 / КОНТАКТИ", "Контактні дані")
                Field(form.contactSurname, { v -> vm.update({ it.copy(contactSurname = v) }, "contact_surname") }, "Прізвище", "contact_surname", ui.errors, focus, locked, 64, name = true)
                Field(form.contactName, { v -> vm.update({ it.copy(contactName = v) }, "contact_name") }, "Ім’я", "contact_name", ui.errors, focus, locked, 128, name = true)
                Field(form.contactPatronymic, { v -> vm.update({ it.copy(contactPatronymic = v) }, "contact_patronymic") }, "По батькові", "contact_patronymic", ui.errors, focus, locked, 64, required = false, name = true)
                Field(form.contactPhone, { v -> vm.update({ it.copy(contactPhone = v) }, "contact_phone") }, "Номер телефону", "contact_phone", ui.errors, focus, locked, 32,
                    keyboard = KeyboardType.Phone, placeholder = "+380XXXXXXXXX")
                Hint("Вхід у Google не потрібний для покупки. Ми зв’яжемося за цим номером щодо замовлення.")
            }

            Panel {
                Step("02 / ДОСТАВКА", "Доставка Новою поштою")
                if (ui.delivery.courierEnabled) listOf("warehouse" to "Відділення / поштомат", "courier" to "Кур’єр").forEach { (method, label) ->
                    Choice(label, form.deliveryMethod == method, !locked) { vm.setMethod(method) }
                }
                Field(form.city, vm::setCity, "Місто / населений пункт", "city", ui.errors, focus, locked, 128, placeholder = "Почніть вводити місто")
                Suggestions(ui.cityOptions, vm::pickCity)
                Field(form.address, vm::setAddress, if (form.deliveryMethod == "courier") "Адреса доставки" else "Номер або адреса відділення / поштомата",
                    "address", ui.errors, focus, locked, 255,
                    placeholder = if (form.deliveryMethod == "courier") "Вулиця, будинок, квартира" else "Відділення №… або поштомат №…")
                Suggestions(ui.warehouseOptions, vm::pickWarehouse)
                if (ui.directoryBusy.isNotEmpty()) InlineMessage("Шукаємо " + if (ui.directoryBusy == "city") "населений пункт…" else "відділення…")
                Hint(ui.deliveryNote.ifEmpty { "Якщо потрібного варіанта немає в довіднику, введіть населений пункт і повну адресу вручну." })
            }

            Panel {
                Step("03 / ОПЛАТА", "Спосіб оплати")
                Choice("Оплата при отриманні", form.paymentMethod == "cod", !locked) { vm.update({ it.copy(paymentMethod = "cod") }) }
                Choice("Переказ за реквізитами після підтвердження менеджером", form.paymentMethod == "card", !locked) { vm.update({ it.copy(paymentMethod = "card") }) }
                Hint("Реквізити надає менеджер після підтвердження замовлення.")
                AccordField(form.comment, { v -> vm.update({ it.copy(comment = v) }) }, "Коментар до замовлення", maxLength = 500, singleLine = false,
                    minLines = 3, placeholder = "Необов’язково", enabled = !locked)
            }

            Panel {
                Step("04 / ПІДТВЕРДЖЕННЯ", "Перевірка замовлення")
                Field(form.promoCode, { v -> vm.update({ it.copy(promoCode = v) }, "promo_code") }, "Промокод", "promo_code", ui.errors, focus, locked, 64, required = false)
                OutlineButton(if (ui.quoting) "Перераховуємо…" else "Перерахувати", vm::recalculate, enabled = !ui.quoting && !cart.blocked && !locked)
                if (session.account.hasSession && (quote?.bonusAvailable ?: java.math.BigDecimal.ZERO) > java.math.BigDecimal.ZERO) {
                    Check("Використати бонуси: до ${formatAmount(quote!!.bonusAvailable)} грн", form.useBonus, !locked) { v -> vm.update({ it.copy(useBonus = v) }) }
                }
                Check("Погоджуюся з умовами покупки, доставки та обробкою персональних даних для оформлення й доставки замовлення",
                    form.termsAccepted, !locked, Modifier.focusRequester(focus.getValue("terms_accepted"))) { v -> vm.update({ it.copy(termsAccepted = v) }, "terms_accepted") }
                ui.errors["terms_accepted"]?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Accord.colors.danger) }
                // What the consent refers to, readable without leaving the form.
                listOf("delivery", "returns").forEach { key ->
                    val (title, text) = BuyerInfo.of(key)
                    Column(Modifier.fillMaxWidth().clickable { docOpen = if (docOpen == key) "" else key }.padding(vertical = 6.dp)) {
                        Text((if (docOpen == key) "▾ " else "▸ ") + title, style = MaterialTheme.typography.bodyMedium, color = Accord.colors.accent)
                        if (docOpen == key) Text(text, style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSecondary, modifier = Modifier.padding(top = 6.dp))
                    }
                }
                Row {
                    TextLink("Публічна оферта", { nav.go(Routes.legal("terms")) })
                    Spacer(Modifier.padding(6.dp))
                    TextLink("Політика конфіденційності", { nav.go(Routes.legal("privacy")) })
                }
            }

            InlineMessage(ui.error, error = true)
            PrimaryButton(when {
                ui.submitting -> "Обробляємо…"
                attempt != null -> "Повторити підтвердження"
                quote != null -> "Підтвердити замовлення"
                else -> "Перевірити суму"
            }, {
                vm.submit { field ->
                    runCatching { focus[field]?.requestFocus() }
                }
            }, Modifier.fillMaxWidth().heightIn(min = 56.dp), enabled = !ui.quoting && !ui.checking && (attempt != null || !cart.blocked), busy = ui.submitting)
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun Step(label: String, title: String) {
    Text(label, style = MaterialTheme.typography.labelMedium, color = Accord.colors.accent)
    Text(title, style = MaterialTheme.typography.headlineSmall)
}

@Composable
private fun Hint(text: String) = Text(text, style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)

@Composable
private fun SummaryRow(label: String, value: String, final: Boolean = false) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(label, Modifier.weight(1f), style = if (final) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodySmall,
            color = if (final) Accord.colors.ink else Accord.colors.textSecondary)
        Text(value, style = if (final) MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Medium) else MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun Field(
    value: String, onChange: (String) -> Unit, label: String, key: String, errors: Map<String, String>,
    focus: Map<String, FocusRequester>, locked: Boolean, max: Int, required: Boolean = true,
    keyboard: KeyboardType = KeyboardType.Text, placeholder: String = "", name: Boolean = false,
) {
    AccordField(value, onChange, label, Modifier.focusRequester(focus.getValue(key)), required = required, error = errors[key],
        placeholder = placeholder, maxLength = max, enabled = !locked,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard, capitalization = if (name) KeyboardCapitalization.Words else KeyboardCapitalization.Sentences))
}

@Composable
private fun Choice(label: String, selected: Boolean, enabled: Boolean, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(selected, enabled = enabled, role = Role.RadioButton, onClick = onClick),
        verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected, null, enabled = enabled)
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
private fun Check(label: String, checked: Boolean, enabled: Boolean, modifier: Modifier = Modifier, onChange: (Boolean) -> Unit) {
    Row(modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(checked, enabled = enabled, role = Role.Checkbox, onValueChange = onChange),
        verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked, null, enabled = enabled)
        Text(label, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
private fun Suggestions(options: List<DirectoryItem>, pick: (DirectoryItem) -> Unit) {
    if (options.isEmpty()) return
    Column(Modifier.fillMaxWidth().border(1.dp, Accord.colors.line)) {
        options.forEach { item ->
            Text(item.label, Modifier.fillMaxWidth().clickable(role = Role.Button) { pick(item) }.padding(horizontal = 14.dp, vertical = 12.dp),
                style = MaterialTheme.typography.bodySmall)
            HorizontalDivider(color = Accord.colors.line)
        }
    }
}

@Composable
fun SuccessScreen(nav: Nav, result: ua.accordniche.shop.data.CheckoutResult?) {
    Scaffold(topBar = { AccordTopBar("Замовлення") }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(Gutter), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            if (result == null || result.orderId <= 0) {
                Text("Перевірка замовлення", style = MaterialTheme.typography.displaySmall)
                Panel {
                    Text("На цій сторінці немає підтвердження нової покупки. Перевірте історію замовлень у своєму профілі.", style = MaterialTheme.typography.bodyMedium)
                    PrimaryButton("Історія замовлень", { nav.tab(Routes.PROFILE) })
                }
                return@Column
            }
            Eyebrow("ACCORD NICHE")
            Text("Дякуємо за замовлення", style = MaterialTheme.typography.displaySmall)
            Panel {
                Text("Замовлення №${result.orderId} прийнято", style = MaterialTheme.typography.headlineSmall)
                Text("Менеджер опрацює його та зв’яжеться за вказаним номером телефону.", style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
                Text("За товари: ${formatAmount(result.total)} грн", style = MaterialTheme.typography.titleMedium)
                Hint("Це підтвердження створення замовлення. Статус оплати й доставки доступний у профілі; для доступу з інших пристроїв увійдіть через Google.")
                PrimaryButton("Історія замовлень", { nav.tab(Routes.PROFILE) }, Modifier.fillMaxWidth())
                OutlineButton("Продовжити покупки", { nav.tab(Routes.catalog()) }, Modifier.fillMaxWidth())
            }
        }
    }
}
