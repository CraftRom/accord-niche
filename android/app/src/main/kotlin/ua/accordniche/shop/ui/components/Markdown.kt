package ua.accordniche.shop.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import ua.accordniche.shop.container
import ua.accordniche.shop.ui.theme.Accord

/** Blocks of the safe Markdown subset the site renders (no raw HTML). */
sealed interface MdBlock {
    data class Heading(val level: Int, val text: String) : MdBlock
    data class Paragraph(val text: String) : MdBlock
    data class Quote(val text: String) : MdBlock
    data class ListBlock(val ordered: Boolean, val items: List<String>) : MdBlock
    data class Code(val text: String) : MdBlock
    data class Image(val alt: String, val src: String) : MdBlock
    data object Rule : MdBlock
}

private val imageLine = Regex("^!\\[([^\\]]*)]\\(([^)\\s]+)(?:\\s+\"[^\"]*\")?\\)$")
private val bullet = Regex("^\\s*[-*+]\\s+(.*)$")
private val numbered = Regex("^\\s*\\d+[.)]\\s+(.*)$")
private val heading = Regex("^(#{1,6})\\s+(.*?)\\s*#*$")

fun parseMarkdown(source: String): List<MdBlock> {
    val blocks = mutableListOf<MdBlock>()
    val lines = source.replace("\r\n", "\n").split('\n')
    var i = 0
    val paragraph = StringBuilder()
    fun flush() {
        if (paragraph.isNotBlank()) blocks += MdBlock.Paragraph(paragraph.toString().trim())
        paragraph.clear()
    }
    while (i < lines.size) {
        val line = lines[i]
        val trimmed = line.trim()
        when {
            trimmed.startsWith("```") -> {
                flush()
                val code = StringBuilder()
                i++
                while (i < lines.size && !lines[i].trim().startsWith("```")) { code.appendLine(lines[i]); i++ }
                blocks += MdBlock.Code(code.toString().trimEnd())
            }
            trimmed.isEmpty() -> flush()
            heading.matches(trimmed) -> {
                flush(); val m = heading.find(trimmed)!!
                blocks += MdBlock.Heading(m.groupValues[1].length, m.groupValues[2])
            }
            Regex("^(-{3,}|\\*{3,}|_{3,})$").matches(trimmed) -> { flush(); blocks += MdBlock.Rule }
            imageLine.matches(trimmed) -> {
                flush(); val m = imageLine.find(trimmed)!!
                blocks += MdBlock.Image(m.groupValues[1], m.groupValues[2])
            }
            trimmed.startsWith(">") -> {
                flush()
                val quote = StringBuilder()
                while (i < lines.size && lines[i].trim().startsWith(">")) { quote.append(lines[i].trim().removePrefix(">").trim()).append(' '); i++ }
                blocks += MdBlock.Quote(quote.toString().trim()); continue
            }
            bullet.matches(line) || numbered.matches(line) -> {
                flush()
                val ordered = numbered.matches(line)
                val pattern = if (ordered) numbered else bullet
                val items = mutableListOf<String>()
                while (i < lines.size && pattern.matches(lines[i])) {
                    items += pattern.find(lines[i])!!.groupValues[1]; i++
                    while (i < lines.size && lines[i].startsWith("  ") && lines[i].isNotBlank() && !pattern.matches(lines[i])) {
                        items[items.lastIndex] = items.last() + " " + lines[i].trim(); i++
                    }
                }
                blocks += MdBlock.ListBlock(ordered, items); continue
            }
            else -> paragraph.append(if (paragraph.isEmpty()) trimmed else " $trimmed")
        }
        i++
    }
    flush()
    return blocks
}

private val inline = Regex("(\\*\\*|__)(.+?)\\1|(\\*|_)(.+?)\\3|`([^`]+)`|!?\\[([^\\]]*)]\\(([^)\\s]+)(?:\\s+\"[^\"]*\")?\\)")

/** Inline emphasis, code and links; only https and site links become tappable. */
fun inlineMarkdown(text: String, linkColor: androidx.compose.ui.graphics.Color, resolve: (String) -> String?): AnnotatedString = buildAnnotatedString {
    var last = 0
    for (m in inline.findAll(text)) {
        append(text.substring(last, m.range.first))
        when {
            m.groups[2] != null -> withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) { append(m.groupValues[2]) }
            m.groups[4] != null -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(m.groupValues[4]) }
            m.groups[5] != null -> withStyle(SpanStyle(fontFamily = FontFamily.Monospace)) { append(m.groupValues[5]) }
            m.value.startsWith("!") -> append(m.groupValues[6])
            else -> {
                val url = resolve(m.groupValues[7])
                if (url != null) withLink(LinkAnnotation.Url(url, TextLinkStyles(SpanStyle(color = linkColor, textDecoration = TextDecoration.Underline)))) {
                    append(m.groupValues[6].ifEmpty { url })
                } else append(m.groupValues[6])
            }
        }
        last = m.range.last + 1
    }
    append(text.substring(last))
}

@Composable
fun MarkdownText(body: String, modifier: Modifier = Modifier) {
    val blocks = remember(body) { parseMarkdown(body) }
    val api = LocalContext.current.container.api
    val link = Accord.colors.accent
    val resolve: (String) -> String? = { href ->
        when {
            href.startsWith("https://") || href.startsWith("mailto:") || href.startsWith("tel:") -> href
            href.startsWith("/") -> api.absolute(href)
            else -> null
        }
    }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(14.dp)) {
        for (block in blocks) when (block) {
            // A Markdown h1 inside the article is shown as h2: the page has its own title.
            is MdBlock.Heading -> Text(inlineMarkdown(block.text, link, resolve), Modifier.padding(top = 8.dp).semantics { heading() },
                style = if (block.level <= 2) MaterialTheme.typography.headlineSmall else MaterialTheme.typography.titleLarge)
            is MdBlock.Paragraph -> Text(inlineMarkdown(block.text, link, resolve), style = MaterialTheme.typography.bodyLarge,
                color = Accord.colors.textSecondary)
            is MdBlock.Quote -> Row(Modifier.height(IntrinsicSize.Min)) {
                Box(Modifier.width(2.dp).fillMaxHeight().background(Accord.colors.gold))
                Text(inlineMarkdown(block.text, link, resolve), Modifier.padding(start = 14.dp),
                    style = MaterialTheme.typography.bodyLarge.copy(fontStyle = FontStyle.Italic), color = Accord.colors.textSecondary)
            }
            is MdBlock.ListBlock -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                block.items.forEachIndexed { index, item ->
                    Row {
                        Text(if (block.ordered) "${index + 1}." else "•", Modifier.width(24.dp), style = MaterialTheme.typography.bodyLarge, color = Accord.colors.accent)
                        Text(inlineMarkdown(item, link, resolve), style = MaterialTheme.typography.bodyLarge, color = Accord.colors.textSecondary)
                    }
                }
            }
            is MdBlock.Code -> Text(block.text, Modifier.fillMaxWidth().background(Accord.colors.soft).padding(12.dp),
                style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace))
            is MdBlock.Image -> {
                val src = block.src
                val safe = src.startsWith("https://") || Regex("^/media/[A-Za-z0-9_-]+\\.(png|jpe?g|gif|webp)$", RegexOption.IGNORE_CASE).matches(src)
                if (safe) AsyncImage(model = api.absolute(src), contentDescription = block.alt, contentScale = ContentScale.FillWidth,
                    modifier = Modifier.fillMaxWidth())
            }
            MdBlock.Rule -> HorizontalDivider(color = Accord.colors.line)
        }
    }
}

