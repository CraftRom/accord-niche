package ua.accordniche.shop.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/** One read request per screen entry: keeps the last data while refreshing, never invents data. */
class RequestViewModel(private val load: suspend () -> Any?) : ViewModel() {
    var data by mutableStateOf<Any?>(null)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<Throwable?>(null)
        private set
    private var job: Job? = null

    init { retry() }

    fun retry() {
        job?.cancel()
        job = viewModelScope.launch {
            loading = true; error = null
            try { data = load() } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel } catch (failure: Exception) {
                error = failure
                if ((failure as? ua.accordniche.shop.data.ApiException)?.notFound == true) data = null
            } finally { loading = false }
        }
    }
}

class Request<T>(private val vm: RequestViewModel) {
    @Suppress("UNCHECKED_CAST")
    val data: T? get() = vm.data as T?
    val loading get() = vm.loading
    val error get() = vm.error
    fun retry() = vm.retry()
}

@Composable
fun <T> rememberRequest(key: String, load: suspend () -> T): Request<T> =
    Request(viewModel(key = key, factory = viewModelFactory { initializer { RequestViewModel(load) } }))

/** Loading / error / content for a request, with a stale-data notice on a failed refresh. */
@Composable
fun <T> RequestContent(request: Request<T>, notFound: String = "Сторінку не знайдено", loadingText: String = "Завантажуємо…", content: @Composable (T) -> Unit) {
    val data = request.data
    val error = request.error
    when {
        data == null && request.loading -> LoadingState(loadingText)
        data == null && error != null -> ErrorState(error, request::retry, notFound)
        data != null -> {
            if (error != null) StateBlock(null, "Не вдалося оновити дані. Показуємо останню завантажену версію.", error = true,
                action = { TextLink("Оновити", request::retry) })
            content(data)
        }
    }
}
