package ua.accordniche.shop.data

import java.net.URLEncoder

private fun enc(value: String) = URLEncoder.encode(value, "UTF-8")

data class CatalogQuery(
    val kind: String = "all",
    val q: String = "",
    val brand: String = "",
    val gender: String = "",
    val volume: Int? = null,
    val available: Boolean = false,
    val sort: String = "recommended",
) {
    fun toQuery(offset: Int, limit: Int = 24): String = buildList {
        add("kind=" + enc(kind))
        if (q.isNotBlank()) add("q=" + enc(q.trim()))
        if (brand.isNotBlank()) add("brand=" + enc(brand))
        if (gender.isNotBlank()) add("gender=" + enc(gender))
        volume?.let { add("volume=$it") }
        if (available) add("available=true")
        if (sort != "recommended") add("sort=" + enc(sort))
        add("limit=$limit"); add("offset=$offset")
    }.joinToString("&")

    val refineCount get() = listOf(brand.isNotBlank(), gender.isNotBlank(), volume != null, available).count { it }
}

/** Public, read-only shop data: catalog, blog and documents. */
class StoreRepository(private val api: ApiClient) {
    suspend fun siteConfig(): SiteConfig = api.get("/api/public/site-config")
    suspend fun storefront(): Storefront = api.get("/api/public/storefront")
    suspend fun aromas(query: CatalogQuery, offset: Int): AromaPage = api.get("/api/public/aromas?" + query.toQuery(offset))
    suspend fun aroma(id: Int): AromaDetail = api.get("/api/public/aromas/$id")
    suspend fun products(ids: Collection<Int>): List<Product> =
        if (ids.isEmpty()) emptyList() else api.get("/api/public/products?ids=" + ids.sorted().joinToString(","))
    suspend fun brands(): List<String> = aromasFacets().brands
    private suspend fun aromasFacets(): AromaPage = api.get("/api/public/aromas?limit=1")

    suspend fun posts(q: String, offset: Int): PostPage =
        api.get("/api/public/blog?q=" + enc(q.trim()) + "&limit=12&offset=$offset")
    suspend fun post(slug: String): PostCard = api.get("/api/public/blog/" + enc(slug).replace("+", "%20"))
    suspend fun comments(slug: String, offset: Int, parentId: Int? = null): CommentPage =
        api.get("/api/public/blog/" + enc(slug).replace("+", "%20") + "/comments?offset=$offset" + (parentId?.let { "&parent_id=$it" } ?: ""))
    suspend fun legal(key: String): LegalDoc = api.get("/api/public/legal/$key")
}
