package ua.accordniche.shop.ui.profile

import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential

/**
 * «Sign in with Google» through Android Credential Manager. The ID token is
 * requested for the shop's web client, so the server verifies it exactly like
 * a website sign-in (the Android client is accepted as the authorized party).
 */
suspend fun requestGoogleIdToken(context: Context, serverClientId: String): Result<String> {
    val option = GetSignInWithGoogleOption.Builder(serverClientId).build()
    val request = GetCredentialRequest.Builder().addCredentialOption(option).build()
    return try {
        val credential = CredentialManager.create(context).getCredential(context, request).credential
        if (credential is CustomCredential && credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            Result.success(GoogleIdTokenCredential.createFrom(credential.data).idToken)
        } else Result.failure(IllegalStateException("Google не повернув облікові дані. Спробуйте ще раз."))
    } catch (cancel: GetCredentialCancellationException) {
        Result.failure(IllegalStateException(""))
    } catch (none: NoCredentialException) {
        Result.failure(IllegalStateException("На пристрої немає облікового запису Google. Додайте його в налаштуваннях телефону."))
    } catch (error: GetCredentialException) {
        Result.failure(IllegalStateException("Не вдалося увійти через Google. Спробуйте ще раз."))
    }
}
