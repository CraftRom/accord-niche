package ua.accordniche.shop.ui.catalog

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Sort
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.InputChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ua.accordniche.shop.AppContainer
import ua.accordniche.shop.data.ApiException
import ua.accordniche.shop.data.Aroma
import ua.accordniche.shop.data.CatalogQuery
import ua.accordniche.shop.ui.Nav
import ua.accordniche.shop.ui.Routes
import ua.accordniche.shop.ui.components.AccordTopBar
import ua.accordniche.shop.ui.components.ErrorState
import ua.accordniche.shop.ui.components.Gutter
import ua.accordniche.shop.ui.components.LoadingState
import ua.accordniche.shop.ui.components.OutlineButton
import ua.accordniche.shop.ui.components.PageTitle
import ua.accordniche.shop.ui.components.PrimaryButton
import ua.accordniche.shop.ui.components.ProductCard
import ua.accordniche.shop.ui.components.StateBlock
import ua.accordniche.shop.ui.components.TextLink
import ua.accordniche.shop.ui.theme.Accord

data class CatalogState(
    val query: CatalogQuery = CatalogQuery(),
    val items: List<Aroma> = emptyList(),
    val total: Int = -1,
    val brands: List<String> = emptyList(),
    val volumes: List<Int> = emptyList(),
    val loading: Boolean = false,
    val loadingMore: Boolean = false,
    val error: Throwable? = null,
) {
    val canLoadMore get() = total >= 0 && items.size < total
}

class CatalogViewModel(private val app: AppContainer, initial: CatalogQuery) : ViewModel() {
    private val _state = MutableStateFlow(CatalogState(query = initial))
    val state = _state.asStateFlow()
    private var job: Job? = null

    init { reload() }

    fun apply(query: CatalogQuery) {
        if (query == _state.value.query) return
        _state.update { it.copy(query = query) }
        reload()
    }

    fun reload() {
        job?.cancel()
        val query = _state.value.query
        job = viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            try {
                val page = app.store.aromas(query, 0)
                _state.update { it.copy(items = page.items, total = page.total, brands = page.brands, volumes = page.volumes, loading = false) }
            } catch (error: ApiException) {
                _state.update { it.copy(loading = false, error = error) }
            }
        }
    }

    fun loadMore() {
        val current = _state.value
        if (current.loading || current.loadingMore || !current.canLoadMore) return
        job = viewModelScope.launch {
            _state.update { it.copy(loadingMore = true) }
            try {
                val page = app.store.aromas(current.query, current.items.size)
                _state.update { state ->
                    val merged = (state.items + page.items).distinctBy { it.key }
                    state.copy(items = merged, total = page.total, loadingMore = false)
                }
            } catch (error: ApiException) {
                _state.update { it.copy(loadingMore = false, error = error) }
            }
        }
    }
}

val kindTitles = linkedMapOf("all" to "Каталог", "hits" to "Хіти продажів", "new" to "Новинки", "recommended" to "Рекомендуємо", "sets" to "Набори пробників")
private val kindChips = linkedMapOf("all" to "Усі", "hits" to "Хіти", "new" to "Новинки", "recommended" to "Рекомендуємо", "sets" to "Набори")
val sortNames = linkedMapOf("recommended" to "Рекомендовані", "popular" to "За продажами", "new" to "Спочатку новинки",
    "price_asc" to "Спочатку дешевші", "price_desc" to "Спочатку дорожчі", "name" to "За назвою")
val genderNames = linkedMapOf("female" to "Жіночий", "male" to "Чоловічий", "unisex" to "Унісекс")

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun CatalogScreen(app: AppContainer, nav: Nav, kind: String, brand: String, q: String) {
    val initial = CatalogQuery(kind = kind.ifBlank { "all" }, brand = brand, q = q)
    val vm: CatalogViewModel = viewModel(key = "catalog:${initial.kind}:$brand:$q",
        factory = viewModelFactory { initializer { CatalogViewModel(app, initial) } })
    val state by vm.state.collectAsStateWithLifecycle()
    val query = state.query
    var search by rememberSaveable { mutableStateOf(query.q) }
    var filters by remember { mutableStateOf(false) }
    var sortMenu by remember { mutableStateOf(false) }
    val focus = LocalFocusManager.current
    val grid = rememberLazyGridState()

    // Typing searches after a short pause, like the site.
    LaunchedEffect(search) {
        if (search.trim() == query.q) return@LaunchedEffect
        delay(300)
        vm.apply(vm.state.value.query.copy(q = search.trim()))
    }
    LaunchedEffect(grid) {
        snapshotFlow { grid.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { last ->
            if (last >= grid.layoutInfo.totalItemsCount - 6) vm.loadMore()
        }
    }

    Scaffold(topBar = {
        AccordTopBar(title = kindTitles[query.kind] ?: "Каталог", onBack = if (nav.controller.previousBackStackEntry != null) nav::back else null)
    }) { padding ->
        PullToRefreshBox(isRefreshing = state.loading && state.items.isNotEmpty(), onRefresh = vm::reload, modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyVerticalGrid(GridCells.Adaptive(160.dp), state = grid, modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = Gutter, end = Gutter, bottom = 24.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Column {
                        PageTitle("КОЛЕКЦІЯ АРОМАТІВ", kindTitles[query.kind] ?: "Каталог",
                            if (query.kind == "hits") "Добірка за фактичними продажами за останні 90 днів. Нові, скасовані та повернені замовлення не впливають на рейтинг."
                            else "Актуальні ціни, доступні об’єми та наявність.", inset = false)
                        OutlinedTextField(value = search, onValueChange = { search = it.take(120) }, modifier = Modifier.fillMaxWidth(),
                            placeholder = { Text("Назва, бренд…") }, singleLine = true, shape = MaterialTheme.shapes.small,
                            leadingIcon = { Icon(Icons.Outlined.Search, null) },
                            trailingIcon = { if (search.isNotEmpty()) IconButton(onClick = { search = "" }) { Icon(Icons.Outlined.Close, "Очистити пошук") } },
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { focus.clearFocus(); vm.apply(query.copy(q = search.trim())) }),
                            colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Accord.colors.gold))
                        Spacer(Modifier.height(10.dp))
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(kindChips.entries.toList(), key = { it.key }) { (key, label) ->
                                FilterChip(selected = query.kind == key, onClick = { vm.apply(query.copy(kind = key)) }, label = { Text(label) },
                                    shape = MaterialTheme.shapes.small, colors = FilterChipDefaults.filterChipColors(
                                        selectedContainerColor = Accord.colors.ink, selectedLabelColor = Accord.colors.surface))
                            }
                        }
                        Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            TextButton(onClick = { filters = true }) {
                                Icon(Icons.Outlined.Tune, null, tint = Accord.colors.ink)
                                Spacer(Modifier.padding(start = 6.dp))
                                Text("Фільтри" + if (query.refineCount > 0) " (${query.refineCount})" else "", color = Accord.colors.ink)
                            }
                            Spacer(Modifier.weight(1f))
                            Column {
                                TextButton(onClick = { sortMenu = true }) {
                                    Icon(Icons.AutoMirrored.Outlined.Sort, null, tint = Accord.colors.ink)
                                    Spacer(Modifier.padding(start = 6.dp))
                                    Text(sortNames[query.sort] ?: "Сортування", color = Accord.colors.ink)
                                }
                                DropdownMenu(sortMenu, { sortMenu = false }) {
                                    sortNames.forEach { (key, label) ->
                                        DropdownMenuItem(text = { Text(label) }, onClick = { sortMenu = false; vm.apply(query.copy(sort = key)) })
                                    }
                                }
                            }
                        }
                        val chips = buildList {
                            if (query.q.isNotBlank()) add("Пошук: «${query.q}»" to { search = ""; vm.apply(query.copy(q = "")) })
                            if (query.brand.isNotBlank()) add("Бренд: ${query.brand}" to { vm.apply(query.copy(brand = "")) })
                            if (query.gender.isNotBlank()) add("Аромат для: ${genderNames[query.gender] ?: query.gender}" to { vm.apply(query.copy(gender = "")) })
                            query.volume?.let { add("$it мл" to { vm.apply(query.copy(volume = null)) }) }
                            if (query.available) add("Лише в наявності" to { vm.apply(query.copy(available = false)) })
                        }
                        if (chips.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            chips.forEach { (label, remove) ->
                                InputChip(selected = false, onClick = remove, label = { Text(label) }, shape = MaterialTheme.shapes.small,
                                    trailingIcon = { Icon(Icons.Outlined.Close, "Прибрати фільтр: $label") })
                            }
                            if (chips.size > 1) TextLink("Очистити все", { search = ""; vm.apply(CatalogQuery(kind = query.kind, sort = query.sort)) })
                        }
                        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                            Text(if (state.total >= 0) "Знайдено ароматів: ${state.total}" else "Завантаження…",
                                style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                            Spacer(Modifier.weight(1f))
                            if (state.loading && state.items.isNotEmpty()) Text("Оновлюємо…", style = MaterialTheme.typography.bodySmall, color = Accord.colors.textSubtle)
                        }
                    }
                }
                val error = state.error
                if (state.items.isEmpty()) item(span = { GridItemSpan(maxLineSpan) }) {
                    when {
                        state.loading -> LoadingState("Завантажуємо товари…")
                        error != null -> ErrorState(error, vm::reload, "Товар недоступний")
                        state.total == 0 -> StateBlock(
                            if (query.kind == "hits") "Хіти ще формуються" else "Нічого не знайдено",
                            if (query.kind == "hits") "Тут з’являться аромати з підтвердженими продажами." else "Спробуйте інший пошук або скиньте фільтри.",
                            action = { OutlineButton("Весь каталог", { search = ""; vm.apply(CatalogQuery()) }) })
                    }
                }
                items(state.items, key = { it.key }) { ProductCard(it, { id -> nav.go(Routes.product(id)) }) }
                if (state.loadingMore) item(span = { GridItemSpan(maxLineSpan) }) {
                    Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator(color = Accord.colors.gold) }
                }
                if (error != null && state.items.isNotEmpty()) item(span = { GridItemSpan(maxLineSpan) }) {
                    StateBlock("Не вдалося завантажити дані", error.message, error = true, action = { TextLink("Спробувати ще раз", vm::loadMore) })
                }
            }
        }
    }

    if (filters) ModalBottomSheet(onDismissRequest = { filters = false }, shape = MaterialTheme.shapes.large) {
        FilterSheet(state, onApply = { vm.apply(it); filters = false }, onReset = { search = ""; vm.apply(CatalogQuery(kind = query.kind)); filters = false })
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FilterSheet(state: CatalogState, onApply: (CatalogQuery) -> Unit, onReset: () -> Unit) {
    var draft by remember { mutableStateOf(state.query) }
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = Gutter).navigationBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Фільтри", style = MaterialTheme.typography.headlineSmall)
        FilterGroup("БРЕНД", listOf("" to "Усі бренди") + state.brands.map { it to it }, draft.brand) { draft = draft.copy(brand = it) }
        FilterGroup("АРОМАТ ДЛЯ", listOf("" to "Для всіх") + genderNames.entries.map { it.key to it.value }, draft.gender) { draft = draft.copy(gender = it) }
        FilterGroup("ОБ’ЄМ", listOf("" to "Усі об’єми") + state.volumes.map { "$it" to "$it мл" }, draft.volume?.toString().orEmpty()) {
            draft = draft.copy(volume = it.toIntOrNull())
        }
        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { draft = draft.copy(available = !draft.available) }, verticalAlignment = Alignment.CenterVertically) {
            Checkbox(draft.available, { draft = draft.copy(available = it) })
            Text("Лише в наявності", style = MaterialTheme.typography.bodyMedium)
        }
        PrimaryButton("Показати", { onApply(draft) }, Modifier.fillMaxWidth())
        TextLink("Скинути фільтри", onReset)
        Spacer(Modifier.height(12.dp))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FilterGroup(title: String, options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.labelMedium, color = Accord.colors.accent)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            options.forEach { (value, label) ->
                FilterChip(selected = selected == value, onClick = { onSelect(value) }, label = { Text(label) }, shape = MaterialTheme.shapes.small,
                    colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Accord.colors.ink, selectedLabelColor = Accord.colors.surface))
            }
        }
    }
}

@Composable
fun BrandsScreen(app: AppContainer, nav: Nav) {
    val request = ua.accordniche.shop.ui.components.rememberRequest("brands") { app.store.brands() }
    Scaffold(topBar = { AccordTopBar("Бренди", onBack = nav::back) }) { padding ->
        LazyVerticalGrid(GridCells.Adaptive(150.dp), Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = Gutter, end = Gutter, bottom = 24.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                Column {
                    PageTitle("ПАРФУМЕРНІ БУДИНКИ", "Бренди", "Бренди, представлені в актуальному каталозі.", inset = false)
                    val data = request.data
                    val error = request.error
                    when {
                        data == null && request.loading -> LoadingState()
                        data == null && error != null -> ErrorState(error, request::retry)
                        data != null && data.isEmpty() -> StateBlock("Поки немає товарів", "Завітайте пізніше.")
                    }
                }
            }
            items(request.data.orEmpty(), key = { it }) { brand ->
                Row(Modifier.heightIn(min = 96.dp).background(Accord.colors.soft).border(1.dp, Accord.colors.line)
                    .clickable { nav.go(Routes.catalog(brand = brand)) }.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(brand, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    Text("→", color = Accord.colors.accent)
                }
            }
        }
    }
}
