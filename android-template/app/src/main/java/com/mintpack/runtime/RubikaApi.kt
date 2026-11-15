package com.mintpack.runtime

import okhttp3.MediaType.Companion.toMediaType
import java.io.ByteArrayOutputStream
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Fixed-origin Rubika Bot API client. Tokens are never logged or added to exceptions. */
object RubikaApi {
    private const val API_ORIGIN = "https://botapi.rubika.ir"
    private const val MAX_RESPONSE_BYTES = 8 * 1024 * 1024
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    @Throws(IOException::class)
    fun request(token: String, method: String, payload: JSONObject): Pair<Int, String> {
        require(token.isNotBlank() && token.length <= 1024) { "توکن خالی یا نامعتبر است." }
        require(method.matches(Regex("^[A-Za-z][A-Za-z0-9]{0,63}$"))) { "نام متد معتبر نیست." }
        val payloadText = payload.toString()
        require(payloadText.length <= 1_000_000) { "بدنه درخواست بیش از حد مجاز است." }

        val url = okhttp3.HttpUrl.Builder()
            .scheme("https")
            .host("botapi.rubika.ir")
            .addPathSegment("v3")
            .addPathSegment(token)
            .addPathSegment(method)
            .build()
        val body = payloadText.toRequestBody(jsonMediaType)
        val request = Request.Builder().url(url).post(body).header("Accept", "application/json").build()
        client.newCall(request).execute().use { response ->
            val responseBody = response.body
            if ((responseBody?.contentLength() ?: -1L) > MAX_RESPONSE_BYTES) {
                throw IOException("پاسخ API بزرگ‌تر از حد مجاز است.")
            }
            val bytes = ByteArrayOutputStream()
            responseBody?.byteStream()?.use { input ->
                val buffer = ByteArray(16 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (bytes.size() + count > MAX_RESPONSE_BYTES) throw IOException("پاسخ API بزرگ‌تر از حد مجاز است.")
                    bytes.write(buffer, 0, count)
                }
            }
            return response.code to String(bytes.toByteArray(), Charsets.UTF_8).ifBlank { "{}" }
        }
    }
}
