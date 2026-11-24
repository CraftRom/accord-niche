package ua.accordniche.shop.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

/** Brand tokens of the website (tokens.css): white, black and warm beige; text passes WCAG AA. */
@Immutable
data class AccordPalette(
    val ink: Color,
    val surface: Color,
    val linen: Color,       // photo backdrop, highlights
    val soft: Color,        // summaries, help panels
    val beige: Color,
    val line: Color,
    val textSecondary: Color,
    val textSubtle: Color,
    val accent: Color,      // eyebrows, brands, text links
    val gold: Color,        // decorative rules
    val danger: Color,
    val dangerSurface: Color,
    val success: Color,
    val inverse: Color,     // dark bands (how it works, footer)
    val onInverse: Color,
    val onInverseMuted: Color,
)

val LightPalette = AccordPalette(
    ink = Color(0xFF111111), surface = Color.White, linen = Color(0xFFF5F1EB), soft = Color(0xFFF7F5F1),
    beige = Color(0xFFEFEAE3), line = Color(0xFFE9E7E3), textSecondary = Color(0xFF5C554D),
    textSubtle = Color(0xFF6B665F), accent = Color(0xFF76624A), gold = Color(0xFFA8977A),
    danger = Color(0xFF8A302B), dangerSurface = Color(0xFFFFF3F1), success = Color(0xFF416E4C),
    inverse = Color(0xFF0A0A0A), onInverse = Color(0xFFF5F1EB), onInverseMuted = Color(0xFFB8B6B0),
)

val DarkPalette = AccordPalette(
    ink = Color(0xFFF5F1EB), surface = Color(0xFF0F0E0D), linen = Color(0xFF1E1B18), soft = Color(0xFF181614),
    beige = Color(0xFF26221E), line = Color(0xFF2E2A26), textSecondary = Color(0xFFC9C2B8),
    textSubtle = Color(0xFFA9A297), accent = Color(0xFFC7AD87), gold = Color(0xFFA8977A),
    danger = Color(0xFFF0A39A), dangerSurface = Color(0xFF2D1715), success = Color(0xFF8FC79C),
    inverse = Color(0xFF1A1816), onInverse = Color(0xFFF5F1EB), onInverseMuted = Color(0xFFB8B6B0),
)

val LocalPalette = staticCompositionLocalOf { LightPalette }

object Accord {
    val colors: AccordPalette @Composable get() = LocalPalette.current
}

private val Sans = FontFamily.SansSerif

val AccordTypography = Typography(
    displayMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Light, fontSize = 40.sp, lineHeight = 43.sp, letterSpacing = (-0.05).em),
    displaySmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Light, fontSize = 34.sp, lineHeight = 38.sp, letterSpacing = (-0.05).em),
    headlineMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Normal, fontSize = 28.sp, lineHeight = 34.sp, letterSpacing = (-0.04).em),
    headlineSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Normal, fontSize = 24.sp, lineHeight = 30.sp, letterSpacing = (-0.04).em),
    titleLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Normal, fontSize = 20.sp, lineHeight = 26.sp, letterSpacing = (-0.03).em),
    titleMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Normal, fontSize = 17.sp, lineHeight = 22.sp, letterSpacing = (-0.02).em),
    titleSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 15.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = Sans, fontSize = 15.sp, lineHeight = 25.sp),
    bodyMedium = TextStyle(fontFamily = Sans, fontSize = 14.sp, lineHeight = 22.sp),
    bodySmall = TextStyle(fontFamily = Sans, fontSize = 12.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, letterSpacing = 0.095.em),
    labelMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 12.sp, letterSpacing = 0.2.em),
    labelSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 11.sp, letterSpacing = 0.05.em),
)

private val Sharp = RoundedCornerShape(0.dp)
val AccordShapes = Shapes(extraSmall = Sharp, small = Sharp, medium = Sharp, large = Sharp, extraLarge = Sharp)

@Composable
fun AccordTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val p = if (dark) DarkPalette else LightPalette
    val scheme = if (dark) darkColorScheme(
        primary = p.ink, onPrimary = p.surface, secondary = p.accent, onSecondary = p.surface,
        background = p.surface, onBackground = p.ink, surface = p.surface, onSurface = p.ink,
        surfaceVariant = p.linen, onSurfaceVariant = p.textSecondary, outline = Color(0xFF4A443D), outlineVariant = p.line,
        error = p.danger, onError = p.surface, secondaryContainer = p.beige, onSecondaryContainer = p.ink,
        surfaceContainer = p.soft, surfaceContainerLow = p.surface, surfaceContainerHigh = p.linen,
        surfaceContainerHighest = p.beige, primaryContainer = p.beige, onPrimaryContainer = p.ink,
    ) else lightColorScheme(
        primary = p.ink, onPrimary = Color.White, secondary = p.accent, onSecondary = Color.White,
        background = p.surface, onBackground = p.ink, surface = p.surface, onSurface = p.ink,
        surfaceVariant = p.linen, onSurfaceVariant = p.textSecondary, outline = Color(0xFFD6D0C7), outlineVariant = p.line,
        error = p.danger, onError = Color.White, secondaryContainer = p.beige, onSecondaryContainer = p.ink,
        surfaceContainer = p.soft, surfaceContainerLow = p.surface, surfaceContainerHigh = p.linen,
        surfaceContainerHighest = p.beige, primaryContainer = p.beige, onPrimaryContainer = p.ink,
    )
    CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = scheme, typography = AccordTypography, shapes = AccordShapes, content = content)
    }
}
