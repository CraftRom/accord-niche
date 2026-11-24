package ua.accordniche.shop.ui.blog

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import coil3.compose.AsyncImage
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.container
import ua.accordniche.shop.data.ApiException
import ua.accordniche.shop.data.Comment
import ua.accordniche.shop.data.PostCard
import ua.accordniche.shop.data.formatDate
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordField
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.ErrorState
import ua.accordniche.shop.ui.components.Eyebrow
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.InlineMessage
import ua.accordniche.shop.ui.components.LoadingState
import ua.accordniche.shop.ui.components.MarkdownText
import ua.accordniche.shop.ui.components.PrimaryButton
import ua.accordniche.shop.ui.components.RequestContent
import ua.accordniche.shop.ui.components.StateBlock
import ua.accordniche.shop.ui.components.StatusChip
import ua.accordniche.shop.ui.components.TextLink
import ua.accordniche.shop.ui.components.rememberRequest
import ua.accordniche.shop.ui.theme.Accord
import java.util.UUID

data class BlogListUi(val q: String = "", val items: List<PostCard> = emptyList(), val total: Int = -1,
                      val loading: Boolean = false, val error: Throwable? = null)

class BlogListViewModel(private val app: AppContainer, q: String) : ViewModel() {
    private val _ui = MutableStateFlow(BlogListUi(q = q))
    val ui = _ui.asStateFlow()
    private var job: Job? = null
    init { search(q) }

    fun search(q: String) {
        job?.cancel()
        _ui.update { BlogListUi(q = q.trim(), loading = true) }
        job = viewModelScope.launch {
            try { val page = app.store.posts(q, 0); _ui.update { it.copy(items = page.items, total = page.total, loading = false) } }
            catch (error: ApiException) { _ui.update { it.copy(loading = false, error = error) } }
        }
    }

    fun more() {
        val ui = _ui.value
        if (ui.loading || ui.total < 0 || ui.items.size >= ui.total) return
        job = viewModelScope.launch {
            _ui.update { it.copy(loading = true, error = null) }
            try { val page = app.store.posts(ui.q, ui.items.size); _ui.update { it.copy(items = (it.items + page.items).distinctBy(PostCard::id), total = page.total, loading = false) } }
            catch (error: ApiException) { _ui.update { it.copy(loading = false, error = error) } }
        }
    }
}

@Composable
fun BlogListScreen(app: AppContainer, nav: Nav, q: String) {
    val vm: BlogListViewModel = viewModel(key = "blog:$q", factory = viewModelFactory { initializer { BlogListViewModel(app, q) } })
    val ui by vm.ui.collectAsStateWithLifecycle()
    var search by rememberSaveable { mutableStateOf(q) }
    val focus = LocalFocusManager.current
    val list = rememberLazyListState()
    LaunchedEffect(list) {
        snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { if (it >= list.layoutInfo.totalItemsCount - 3) vm.more() }
    }
    Scaffold(topBar = { AccordTopBar("Блог") }) { padding ->
        PullToRefreshBox(ui.loading && ui.items.isNotEmpty(), { vm.search(ui.q) }, Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(Modifier.fillMaxSize(), state = list) {
                item {
                    Column(Modifier.padding(Gutter), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Eyebrow("Журнал ACCORD NICHE")
                        Text("Блог", style = MaterialTheme.typography.displaySmall)
                        Text("Про аромати, знайомство з парфумерією та життя магазину.", style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
                        OutlinedTextField(search, { search = it.take(120) }, Modifier.fillMaxWidth(), singleLine = true, shape = MaterialTheme.shapes.small,
                            placeholder = { Text("Знайти публікацію…") }, leadingIcon = { Icon(Icons.Outlined.Search, null) },
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { focus.clearFocus(); vm.search(search) }),
                            colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Accord.colors.gold))
                    }
                }
                val error = ui.error
                if (ui.items.isEmpty()) item {
                    when {
                        ui.loading -> LoadingState("Завантажуємо блог…")
                        error != null -> ErrorState(error, { vm.search(ui.q) }, "Публікацію не знайдено")
                        ui.total == 0 -> StateBlock(if (ui.q.isNotEmpty()) "Публікацій не знайдено" else "Скоро тут з’являться публікації",
                            if (ui.q.isNotEmpty()) "Спробуйте інший пошуковий запит." else "Нові матеріали редакції будуть доступні на цій сторінці.")
                    }
                }
                items(ui.items, key = { it.id }) { post ->
                    Column(Modifier.fillMaxWidth().padding(horizontal = Gutter, vertical = 8.dp).border(1.dp, Accord.colors.line)
                        .clickable { nav.go(Routes.article(post.slug)) }) {
                        val cover = LocalContext.current.container.api.absolute(post.coverUrl)
                        if (cover != null) AsyncImage(cover, null, Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(Accord.colors.linen), contentScale = ContentScale.Crop)
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("${formatDate(post.publishedAt)} · ${post.readingMinutes} хв читання", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                            Text(post.title, style = MaterialTheme.typography.titleLarge)
                            if (post.excerpt.isNotBlank()) Text(post.excerpt, style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSecondary)
                            Text("Читати →", style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium), color = Accord.colors.accent)
                            HorizontalDivider(color = Accord.colors.line)
                            Text("${post.authorName} · Коментарів: ${post.commentCount}", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                        }
                    }
                }
                if (ui.loading && ui.items.isNotEmpty()) item {
                    Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator(color = Accord.colors.gold) }
                }
            }
        }
    }
}

private val COMMENT_STATUS = mapOf("pending" to ("warn" to "На модерації · бачите лише ви"), "approved" to ("ok" to "Опубліковано"),
    "rejected" to ("off" to "Не схвалено редакцією"))

@Composable
fun BlogArticleScreen(app: AppContainer, nav: Nav, slug: String) {
    val request = rememberRequest<PostCard>("post:$slug") { app.store.post(slug) }
    Scaffold(topBar = {
        AccordTopBar("Блог", onBack = nav::back, actions = {
            request.data?.let { post -> IconButton(onClick = { nav.share(post.title + "\n" + app.baseUrl + "/blog/" + post.slug) }) { Icon(Icons.Outlined.Share, "Поділитися") } }
        })
    }) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding).imePadding()) {
            item {
                RequestContent(request, notFound = "Публікацію не знайдено", loadingText = "Завантажуємо блог…") { post ->
                    Column(Modifier.padding(Gutter), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("${formatDate(post.publishedAt)} · ${post.readingMinutes} хв читання", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                        Text(post.title, style = MaterialTheme.typography.displaySmall)
                        if (post.excerpt.isNotBlank()) Text(post.excerpt, style = MaterialTheme.typography.bodyLarge, color = Accord.colors.textSecondary)
                        Text(post.authorName, style = MaterialTheme.typography.labelMedium, color = Accord.colors.accent)
                        app.api.absolute(post.coverUrl)?.let { AsyncImage(it, null, Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth) }
                        MarkdownText(post.body, Modifier.padding(top = 8.dp))
                    }
                    Comments(app, nav, post, request::retry)
                }
            }
        }
    }
}

@Composable
private fun Comments(app: AppContainer, nav: Nav, post: PostCard, onChanged: () -> Unit) {
    val session by app.account.state.collectAsStateWithLifecycle()
    val authenticated = session.account.canComment
    var page by rememberSaveable { mutableIntStateOf(1) }
    var revision by remember { mutableIntStateOf(0) }
    val visible = rememberRequest("comments:${post.id}:$page:$revision") { app.store.comments(post.slug, (page - 1) * 10) }
    val mine = rememberRequest("mine:${post.id}:$revision:${session.account.accountKey}") { if (authenticated) app.account.myComments(post.id) else emptyList() }
    var body by rememberSaveable { mutableStateOf("") }
    var clientKey by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
    var replyTo by remember { mutableStateOf<Comment?>(null) }
    var editing by remember { mutableStateOf<Comment?>(null) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    var removing by remember { mutableStateOf<Comment?>(null) }
    val scope = rememberCoroutineScope()

    fun reset() { body = ""; editing = null; replyTo = null; clientKey = UUID.randomUUID().toString() }
    fun submit() {
        if (busy) return
        busy = true; error = ""; message = ""
        scope.launch {
            try {
                val wasEditing = editing
                if (wasEditing != null) app.account.editComment(wasEditing.id, body, wasEditing.version)
                else app.account.comment(post.id, body, replyTo?.id, clientKey)
                reset()
                message = if (wasEditing != null) "Зміни надіслано на модерацію. До схвалення коментар має статус «На модерації» у блоці «Ваші коментарі»."
                    else "Коментар надіслано на модерацію. Його видно у блоці «Ваші коментарі» зі статусом «На модерації»; після схвалення його побачать усі."
                revision++; onChanged()
            } catch (e: ApiException) { error = e.message.orEmpty() } finally { busy = false }
        }
    }

    Column(Modifier.fillMaxWidth().background(Accord.colors.soft).padding(Gutter), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Обговорення", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            Text("Коментарів: ${post.commentCount}", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
        }
        RequestContent(visible, loadingText = "Завантажуємо коментарі…") { data ->
            if (data.items.isEmpty()) Text("Схвалених коментарів поки немає.", style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSubtle)
            data.items.forEach { comment ->
                Thread(app, post.slug, comment, canReply = authenticated && post.commentsEnabled) {
                    editing = null; replyTo = it; clientKey = UUID.randomUUID().toString()
                }
            }
            if (data.total > 10) Row(verticalAlignment = Alignment.CenterVertically) {
                TextLink("← Назад", { page-- }, enabled = page > 1)
                Text("$page", Modifier.padding(horizontal = 12.dp))
                TextLink("Далі →", { page++ }, enabled = page * 10 < data.total)
            }
        }
        if (authenticated) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Ваші коментарі", style = MaterialTheme.typography.titleMedium)
            RequestContent(mine) { own ->
                if (own.isEmpty()) Text("Ви ще не коментували цю статтю.", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                own.forEach { comment ->
                    Column(Modifier.fillMaxWidth().background(Accord.colors.surface).border(1.dp, Accord.colors.line).padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        val (tone, label) = COMMENT_STATUS[comment.status] ?: ("off" to (comment.status ?: ""))
                        StatusChip(tone, label)
                        Text(comment.body, style = MaterialTheme.typography.bodyMedium)
                        Row {
                            if (post.commentsEnabled) TextLink("Редагувати", { editing = comment; replyTo = null; body = comment.body }, enabled = !busy)
                            TextLink("Видалити", { removing = comment }, enabled = !busy, danger = true)
                        }
                    }
                }
            }
        }
        InlineMessage(error, error = true)
        if (message.isNotEmpty()) Text(message, style = MaterialTheme.typography.bodySmall, color = Accord.colors.success)
        when {
            !post.commentsEnabled -> Text("Нові коментарі до цієї публікації закрито.", style = MaterialTheme.typography.bodyMedium, color = Accord.colors.textSubtle)
            authenticated -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(if (editing != null) "Редагувати свій коментар" else "Залишити коментар", style = MaterialTheme.typography.titleMedium)
                replyTo?.takeIf { editing == null }?.let {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Відповідаєте: ${it.authorName}", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                        TextLink("Скасувати відповідь", { reset() }, enabled = !busy)
                    }
                }
                AccordField(body, { body = it; if (editing == null) clientKey = UUID.randomUUID().toString() }, "Ваш коментар",
                    singleLine = false, minLines = 4, maxLength = 2000, enabled = !busy)
                Text("${body.length} / 2000", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                Text("Коментарі публікуються після перевірки редакцією. Відредагований коментар перевіряється знову. Не залишайте в тексті телефон, адресу чи інші особисті дані.",
                    style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                PrimaryButton(if (busy) "Надсилаємо…" else "Надіслати на модерацію", ::submit, Modifier.fillMaxWidth(), enabled = body.trim().length >= 2, busy = busy)
                if (editing != null) TextLink("Скасувати редагування", { reset() }, enabled = !busy)
            }
            else -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Щоб залишити коментар, увійдіть в особистий кабінет.", style = MaterialTheme.typography.bodyMedium)
                PrimaryButton("Увійти та коментувати", { nav.tab(Routes.PROFILE) })
            }
        }
        Spacer(Modifier.height(24.dp))
    }

    removing?.let { comment ->
        AlertDialog(onDismissRequest = { removing = null }, title = { Text("Видалити свій коментар?") },
            confirmButton = { TextButton(onClick = {
                removing = null; busy = true; error = ""
                scope.launch {
                    try { app.account.deleteComment(comment.id, comment.version); message = "Коментар видалено."; revision++; onChanged() }
                    catch (e: ApiException) { error = e.message.orEmpty() } finally { busy = false }
                }
            }) { Text("Видалити", color = Accord.colors.danger) } },
            dismissButton = { TextButton(onClick = { removing = null }) { Text("Залишити", color = Accord.colors.ink) } })
    }
}

@Composable
private fun Thread(app: AppContainer, slug: String, comment: Comment, canReply: Boolean, onReply: (Comment) -> Unit) {
    var open by rememberSaveable(comment.id) { mutableStateOf(false) }
    var page by rememberSaveable(comment.id) { mutableIntStateOf(1) }
    Column(Modifier.fillMaxWidth().background(Accord.colors.surface).border(1.dp, Accord.colors.line).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        CommentHead(comment)
        Text(comment.body, style = MaterialTheme.typography.bodyMedium)
        Row {
            if (canReply) TextLink("Відповісти", { onReply(comment) })
            if (comment.replyCount > 0) TextLink("Відповіді (${comment.replyCount}) " + if (open) "↑" else "↓", { open = !open })
        }
        if (open) {
            val replies = rememberRequest("replies:${comment.id}:$page:${comment.replyCount}") { app.store.comments(slug, (page - 1) * 10, comment.id) }
            Column(Modifier.padding(start = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                RequestContent(replies) { data ->
                    data.items.forEach { reply ->
                        Column { CommentHead(reply); Text(reply.body, style = MaterialTheme.typography.bodyMedium) }
                    }
                    if (data.total > 10) Row {
                        TextLink("←", { page-- }, enabled = page > 1); Text("$page", Modifier.padding(12.dp)); TextLink("→", { page++ }, enabled = page * 10 < data.total)
                    }
                }
            }
        }
    }
}

@Composable
private fun CommentHead(comment: Comment) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(comment.authorName, style = MaterialTheme.typography.titleSmall)
        if (comment.isStaff) StatusChip("warn", "Редакція")
        Text(formatDate(comment.createdAt), style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
    }
}
