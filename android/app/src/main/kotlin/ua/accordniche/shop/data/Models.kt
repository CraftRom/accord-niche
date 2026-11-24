package ua.accordniche.shop.data

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonPrimitive
import java.math.BigDecimal

/** Money arrives as "123.00" (pydantic Decimal) or 123.0 (plain dicts): both become BigDecimal. */
object DecimalSerializer : KSerializer<BigDecimal> {
    override val descriptor = PrimitiveSerialDescriptor("Decimal", PrimitiveKind.STRING)
    override fun deserialize(decoder: Decoder): BigDecimal {
        val raw = if (decoder is JsonDecoder) {
            val element = decoder.decodeJsonElement()
            if (element is JsonNull) "0" else element.jsonPrimitive.content
        } else decoder.decodeString()
        return raw.toBigDecimalOrNull() ?: BigDecimal.ZERO
    }
    override fun serialize(encoder: Encoder, value: BigDecimal) = encoder.encodeString(value.toPlainString())
}

typealias Money = @Serializable(with = DecimalSerializer::class) BigDecimal

@Serializable
data class SiteConfig(
    @SerialName("miniapp_url") val miniappUrl: String = "",
    @SerialName("instagram_url") val instagramUrl: String = "",
    @SerialName("tiktok_url") val tiktokUrl: String = "",
    val phone: String = "",
    @SerialName("seller_name") val sellerName: String = "",
    val email: String = "",
)

/** One sellable volume (SKU). */
@Serializable
data class Product(
    val id: Int,
    val name: String,
    val brand: String = "",
    val gender: String = "unisex",
    @SerialName("volume_ml") val volumeMl: Int? = null,
    @SerialName("is_featured") val isFeatured: Boolean = false,
    @SerialName("is_new") val isNew: Boolean = false,
    val description: String? = null,
    val price: Money,
    val stock: Int = 0,
    @SerialName("photo_url") val photoUrl: String? = null,
    @SerialName("photo_endpoint") val photoEndpoint: String? = null,
    @SerialName("old_price") val oldPrice: Money? = null,
    @SerialName("is_sale") val isSale: Boolean = false,
) {
    val image: String? get() = photoUrl ?: photoEndpoint
}

/** One aroma with its volumes. */
@Serializable
data class Aroma(
    val id: Int,
    @SerialName("default_product_id") val defaultProductId: Int,
    val key: String,
    val name: String,
    val brand: String = "",
    val gender: String = "unisex",
    val description: String = "",
    val variants: List<Product> = emptyList(),
    val stock: Int = 0,
    @SerialName("min_price") val minPrice: Money,
    @SerialName("price_per_ml") val pricePerMl: Money? = null,
    val image: String = "",
    val volumes: List<Int> = emptyList(),
    @SerialName("is_new") val isNew: Boolean = false,
    @SerialName("is_featured") val isFeatured: Boolean = false,
    @SerialName("is_set") val isSet: Boolean = false,
    @SerialName("bestseller_rank") val bestsellerRank: Int? = null,
) {
    val isHit: Boolean get() = (bestsellerRank ?: 0) in 1..8
}

@Serializable
data class Storefront(
    val hits: List<Aroma> = emptyList(),
    val recommended: List<Aroma> = emptyList(),
    @SerialName("new_arrivals") val newArrivals: List<Aroma> = emptyList(),
    val selection: List<Aroma> = emptyList(),
    val total: Int = 0,
    val available: Int = 0,
    @SerialName("window_days") val windowDays: Int = 90,
)

@Serializable
data class AromaPage(
    val items: List<Aroma> = emptyList(),
    val total: Int = 0,
    val limit: Int = 24,
    val offset: Int = 0,
    val brands: List<String> = emptyList(),
    val volumes: List<Int> = emptyList(),
)

@Serializable
data class AromaDetail(val item: Aroma, val related: List<Aroma> = emptyList())

@Serializable
data class Account(
    @SerialName("signed_in") val signedIn: Boolean = false,
    @SerialName("has_session") val hasSession: Boolean = false,
    @SerialName("account_key") val accountKey: String? = null,
    val name: String = "",
    val email: String? = null,
    val phone: String? = null,
    @SerialName("phone_verified") val phoneVerified: Boolean = false,
    @SerialName("telegram_linked") val telegramLinked: Boolean = false,
) {
    /** May comment in the blog: any proven identity. */
    val canComment: Boolean get() = signedIn || phoneVerified || telegramLinked
}

@Serializable
data class WebSession(
    val csrf: String,
    val account: Account = Account(),
    @SerialName("google_client_id") val googleClientId: String = "",
    @SerialName("phone_sms_enabled") val phoneSmsEnabled: Boolean = false,
    @SerialName("phone_telegram_enabled") val phoneTelegramEnabled: Boolean = false,
)

@Serializable
data class CartLine(@SerialName("product_id") val productId: Int, val qty: Int)

@Serializable
data class QuoteRequest(
    val items: List<CartLine>,
    @SerialName("promo_code") val promoCode: String?,
    @SerialName("use_bonus") val useBonus: Boolean,
)

@Serializable
data class QuoteLine(
    @SerialName("product_id") val productId: Int,
    val qty: Int,
    val name: String = "",
    @SerialName("unit_price") val unitPrice: Money,
    @SerialName("line_total") val lineTotal: Money,
)

@Serializable
data class Quote(
    @SerialName("quote_token") val quoteToken: String,
    val subtotal: Money = BigDecimal.ZERO,
    val discount: Money = BigDecimal.ZERO,
    @SerialName("bonus_used") val bonusUsed: Money = BigDecimal.ZERO,
    @SerialName("bonus_available") val bonusAvailable: Money = BigDecimal.ZERO,
    val total: Money = BigDecimal.ZERO,
    val items: List<QuoteLine> = emptyList(),
)

@Serializable
data class Attribution(
    val source: String = "accord_android",
    val medium: String = "app",
    val campaign: String = "",
    val content: String = "",
    val term: String = "",
    @SerialName("session_id") val sessionId: String? = null,
)

@Serializable
data class CheckoutPayload(
    @SerialName("contact_surname") val contactSurname: String,
    @SerialName("contact_name") val contactName: String,
    @SerialName("contact_patronymic") val contactPatronymic: String?,
    @SerialName("contact_phone") val contactPhone: String,
    val city: String,
    val address: String,
    @SerialName("delivery_method") val deliveryMethod: String,
    @SerialName("delivery_city_ref") val deliveryCityRef: String?,
    @SerialName("delivery_warehouse_ref") val deliveryWarehouseRef: String?,
    @SerialName("payment_method") val paymentMethod: String,
    @SerialName("promo_code") val promoCode: String?,
    val comment: String?,
    @SerialName("use_bonus") val useBonus: Boolean,
    @SerialName("terms_accepted") val termsAccepted: Boolean,
    @SerialName("quote_token") val quoteToken: String,
    @SerialName("checkout_key") val checkoutKey: String,
    val attribution: Attribution,
)

@Serializable
data class CheckoutResult(
    @SerialName("order_id") val orderId: Long = 0,
    val total: Money = BigDecimal.ZERO,
    @SerialName("payment_method") val paymentMethod: String? = null,
    val found: Boolean = true,
)

/** A submitted order kept until its result is known, so a retry never duplicates it. */
@Serializable
data class CheckoutAttempt(
    val payload: CheckoutPayload,
    val lines: List<AttemptLine>,
    val total: Money,
)

@Serializable
data class AttemptLine(val product: Product, val qty: Int)

@Serializable
data class CheckoutDefaults(
    @SerialName("contact_surname") val contactSurname: String = "",
    @SerialName("contact_name") val contactName: String = "",
    @SerialName("contact_patronymic") val contactPatronymic: String = "",
    @SerialName("contact_phone") val contactPhone: String = "",
    val city: String = "",
    val address: String = "",
    @SerialName("delivery_method") val deliveryMethod: String = "",
    @SerialName("delivery_city_ref") val deliveryCityRef: String = "",
    @SerialName("delivery_warehouse_ref") val deliveryWarehouseRef: String = "",
    @SerialName("payment_method") val paymentMethod: String = "cod",
)

@Serializable
data class DeliveryConfig(
    @SerialName("courier_enabled") val courierEnabled: Boolean = false,
    @SerialName("novaposhta_enabled") val novaposhtaEnabled: Boolean = false,
)

@Serializable
data class DirectoryItem(
    val ref: String,
    val label: String,
    @SerialName("settlement_ref") val settlementRef: String? = null,
)

@Serializable
data class DirectoryResult(val items: List<DirectoryItem> = emptyList(), val manual: Boolean = false)

@Serializable
data class OrderItem(val name: String, val qty: Int, val price: Money)

@Serializable
data class Order(
    val id: Long,
    val status: String,
    @SerialName("status_label") val statusLabel: String? = null,
    @SerialName("status_source") val statusSource: String = "local",
    @SerialName("crm_status_name") val crmStatusName: String? = null,
    val total: Money,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("operator_name") val operatorName: String? = null,
    @SerialName("tracking_number") val trackingNumber: String? = null,
    @SerialName("can_cancel") val canCancel: Boolean = false,
    val items: List<OrderItem> = emptyList(),
)

@Serializable
data class OrderPage(val items: List<Order> = emptyList(), @SerialName("has_more") val hasMore: Boolean = false)

@Serializable
data class LatestDelivery(val city: String = "", val address: String = "")

@Serializable
data class Profile(
    @SerialName("orders_count") val ordersCount: Int = 0,
    @SerialName("bonus_balance") val bonusBalance: Money = BigDecimal.ZERO,
    @SerialName("latest_delivery") val latestDelivery: LatestDelivery? = null,
)

@Serializable
data class Note(val note: String? = null, val url: String? = null)

@Serializable
data class PostCard(
    val id: Int,
    val slug: String,
    val title: String,
    val excerpt: String = "",
    @SerialName("cover_url") val coverUrl: String = "",
    @SerialName("author_name") val authorName: String = "",
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("reading_minutes") val readingMinutes: Int = 1,
    @SerialName("comment_count") val commentCount: Int = 0,
    val body: String = "",
    @SerialName("comments_enabled") val commentsEnabled: Boolean = false,
)

@Serializable
data class PostPage(val items: List<PostCard> = emptyList(), val total: Int = 0)

@Serializable
data class Comment(
    val id: Int,
    @SerialName("parent_id") val parentId: Int? = null,
    @SerialName("author_name") val authorName: String = "",
    @SerialName("is_staff") val isStaff: Boolean = false,
    val body: String = "",
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("reply_count") val replyCount: Int = 0,
    val status: String? = null,
    val version: Int = 1,
)

@Serializable
data class CommentPage(val items: List<Comment> = emptyList(), val total: Int = 0)

@Serializable
data class LegalDoc(val key: String = "", val title: String = "", val body: String = "")
