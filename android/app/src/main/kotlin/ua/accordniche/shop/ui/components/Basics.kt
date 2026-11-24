package ua.accordniche.shop.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.graphics.Color
import ua.accordniche.shop.data.ApiException
import ua.accordniche.shop.ui.theme.Accord

val Gutter = 18.dp

/** Letter-spaced uppercase label above titles («КОЛЕКЦІЯ АРОМАТІВ»). */
@Composable
fun Eyebrow(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), modifier = modifier, style = MaterialTheme.typography.labelMedium, color = Accord.colors.accent)
}

@Composable
fun PageTitle(label: String, title: String, detail: String? = null, modifier: Modifier = Modifier, inset: Boolean = true) {
    Column(modifier.padding(horizontal = if (inset) Gutter else 0.dp).padding(top = 28.dp, bottom = 20.dp)) {
        Eyebrow(label)
        Spacer(Modifier.height(10.dp))
        Text(title, style = MaterialTheme.typography.displaySmall, modifier = Modifier.semantics { heading() })
        if (!detail.isNullOrBlank()) {
            Spacer(Modifier.height(12.dp))
            Text(detail, style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
        }
    }
}

@Composable
fun SectionHeading(title: String, modifier: Modifier = Modifier, light: Boolean = false) {
    Text(title, modifier = modifier.semantics { heading() }, style = MaterialTheme.typography.headlineMedium,
        color = if (light) Accord.colors.onInverse else MaterialTheme.colorScheme.onBackground)
}

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, busy: Boolean = false) {
    Button(onClick = onClick, enabled = enabled && !busy, modifier = modifier.heightIn(min = 50.dp),
        shape = MaterialTheme.shapes.small, contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
        colors = ButtonDefaults.buttonColors(containerColor = Accord.colors.ink, contentColor = Accord.colors.surface,
            disabledContainerColor = Accord.colors.ink.copy(alpha = 0.4f), disabledContentColor = Accord.colors.surface)) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = Accord.colors.surface)
            Spacer(Modifier.width(10.dp))
        }
        Text(text.uppercase(), style = MaterialTheme.typography.labelLarge, maxLines = 1)
    }
}

@Composable
fun OutlineButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    OutlinedButton(onClick = onClick, enabled = enabled, modifier = modifier.heightIn(min = 48.dp), shape = MaterialTheme.shapes.small,
        border = BorderStroke(1.dp, if (enabled) Accord.colors.ink else Accord.colors.line),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 10.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = Accord.colors.ink)) {
        Text(text.uppercase(), style = MaterialTheme.typography.labelLarge, maxLines = 1)
    }
}

@Composable
fun TextLink(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, danger: Boolean = false) {
    TextButton(onClick = onClick, enabled = enabled, modifier = modifier.heightIn(min = 44.dp), shape = MaterialTheme.shapes.small,
        contentPadding = PaddingValues(horizontal = 4.dp, vertical = 8.dp)) {
        Text(text, style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
            color = if (danger) Accord.colors.danger else Accord.colors.accent)
    }
}

@Composable
fun AccordField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    required: Boolean = false,
    error: String? = null,
    placeholder: String = "",
    maxLength: Int = 255,
    keyboard: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = true,
    minLines: Int = 1,
    enabled: Boolean = true,
    keyboardOptions: KeyboardOptions? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { onValueChange(it.take(maxLength)) },
        modifier = modifier.fillMaxWidth(),
        label = { Text(label + if (required) " *" else "") },
        placeholder = if (placeholder.isNotEmpty()) ({ Text(placeholder, color = Accord.colors.textSubtle) }) else null,
        isError = !error.isNullOrBlank(),
        supportingText = if (!error.isNullOrBlank()) ({ Text(error) }) else null,
        singleLine = singleLine,
        minLines = minLines,
        enabled = enabled,
        shape = MaterialTheme.shapes.small,
        keyboardOptions = keyboardOptions ?: KeyboardOptions(keyboardType = keyboard),
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Accord.colors.gold, unfocusedBorderColor = MaterialTheme.colorScheme.outline,
            focusedLabelColor = Accord.colors.accent),
    )
}

/** One system for loading, error and empty states: says what happened, offers the next step. */
@Composable
fun StateBlock(
    title: String?,
    text: String? = null,
    modifier: Modifier = Modifier,
    loading: Boolean = false,
    error: Boolean = false,
    action: (@Composable () -> Unit)? = null,
) {
    Column(modifier.fillMaxWidth().padding(horizontal = Gutter, vertical = 24.dp)
        .border(1.dp, if (error) Accord.colors.danger.copy(alpha = 0.35f) else Accord.colors.line)
        .background(if (error) Accord.colors.dangerSurface else Accord.colors.soft)
        .padding(22.dp).semantics { liveRegion = if (error) LiveRegionMode.Assertive else LiveRegionMode.Polite },
        horizontalAlignment = Alignment.Start, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (loading) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Accord.colors.gold)
        if (!title.isNullOrBlank()) Text(title, style = MaterialTheme.typography.titleLarge)
        if (!text.isNullOrBlank()) Text(text, style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
        action?.invoke()
    }
}

fun errorTitle(error: Throwable?, notFound: String = "Сторінку не знайдено"): String = when {
    error is ApiException && error.notFound -> notFound
    error is ApiException && error.offline -> "Немає зв’язку з магазином"
    else -> "Не вдалося завантажити дані"
}

@Composable
fun ErrorState(error: Throwable, onRetry: () -> Unit, notFound: String = "Сторінку не знайдено") {
    StateBlock(errorTitle(error, notFound), error.message, error = true, action = { OutlineButton("Спробувати ще раз", onRetry) })
}

@Composable
fun LoadingState(text: String = "Завантажуємо…") = StateBlock(null, text, loading = true)

@Composable
fun InlineMessage(text: String, error: Boolean = false, modifier: Modifier = Modifier) {
    if (text.isBlank()) return
    Text(text, modifier = modifier.fillMaxWidth()
        .then(if (error) Modifier.background(Accord.colors.dangerSurface).border(1.dp, Accord.colors.danger.copy(alpha = .3f)).padding(14.dp) else Modifier.padding(vertical = 6.dp))
        .semantics { liveRegion = if (error) LiveRegionMode.Assertive else LiveRegionMode.Polite },
        style = MaterialTheme.typography.bodySmall, color = if (error) Accord.colors.danger else Accord.colors.textSubtle)
}

/** A card says what it is for and its state in words. */
@Composable
fun StatusChip(tone: String, label: String) {
    val (fg, bg) = when (tone) {
        "ok" -> Accord.colors.success to Accord.colors.success.copy(alpha = 0.1f)
        "warn" -> Accord.colors.accent to Accord.colors.linen
        else -> Accord.colors.textSubtle to Accord.colors.soft
    }
    Text(label, modifier = Modifier.background(bg).border(1.dp, fg.copy(alpha = 0.3f)).padding(horizontal = 8.dp, vertical = 4.dp),
        style = MaterialTheme.typography.labelSmall, color = fg)
}

@Composable
fun Panel(modifier: Modifier = Modifier, soft: Boolean = false, content: @Composable () -> Unit) {
    Column(modifier.fillMaxWidth().border(1.dp, Accord.colors.line).background(if (soft) Accord.colors.soft else Accord.colors.surface).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) { content() }
}

@Composable
fun QtyControl(qty: Int, onChange: (Int) -> Unit, max: Int, name: String, onRemove: (() -> Unit)? = null) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        QtyButton("−", "Зменшити кількість: $name") { onChange(qty - 1) }
        Text("$qty", Modifier.width(28.dp), style = MaterialTheme.typography.titleSmall, textAlign = TextAlign.Center)
        QtyButton("+", "Збільшити кількість: $name", enabled = qty < max && qty < 99) { onChange(qty + 1) }
        if (onRemove != null) {
            Spacer(Modifier.weight(1f))
            TextLink("Видалити", onRemove, danger = true)
        }
    }
}

@Composable
private fun QtyButton(label: String, description: String, enabled: Boolean = true, onClick: () -> Unit) {
    Box(Modifier.size(40.dp).border(1.dp, if (enabled) MaterialTheme.colorScheme.outline else Accord.colors.line)
        .clickable(enabled = enabled, onClickLabel = description, onClick = onClick)
        .semantics { contentDescription = description }, contentAlignment = Alignment.Center) {
        Text(label, style = MaterialTheme.typography.titleMedium, color = if (enabled) Accord.colors.ink else Accord.colors.textSubtle)
    }
}

/** Brand mark from the site header: ACCORD with NICHE between two rules. */
@Composable
fun Logo(modifier: Modifier = Modifier, color: Color = Accord.colors.ink) {
    Column(modifier.width(112.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("ACCORD", style = MaterialTheme.typography.titleLarge.copy(letterSpacing = 0.24.em), color = color)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f).height(1.dp).background(Accord.colors.gold))
            Text(" NICHE ", style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 0.5.em, fontSize = 8.sp), color = color)
            Box(Modifier.weight(1f).height(1.dp).background(Accord.colors.gold))
        }
    }
}
