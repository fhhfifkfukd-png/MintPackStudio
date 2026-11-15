package com.mintpack.runtime

import android.content.Context
import org.json.JSONObject
import java.util.UUID

class BotStore(context: Context) {
    private val prefs = context.getSharedPreferences("mintpack_bots", Context.MODE_PRIVATE)
    private val secretStore = SecretStore()

    data class BotRecord(val id: String, val label: String)

    @Synchronized
    fun add(label: String, token: String): BotRecord {
        require(token.isNotBlank() && token.length <= 1024) { "توکن خالی یا بیش از حد طولانی است." }
        val id = UUID.randomUUID().toString()
        val safeLabel = label.trim().take(48).ifBlank { "ربات ${id.take(6)}" }
        check(prefs.edit().putString("token.$id", secretStore.encrypt(token))
            .putString("label.$id", safeLabel).commit()) { "ذخیره امن توکن ناموفق بود." }
        return BotRecord(id, prefs.getString("label.$id", "ربات") ?: "ربات")
    }

    fun token(id: String): String? = prefs.getString("token.$id", null)?.let(secretStore::decrypt)
    fun offset(id: String): String? = prefs.getString("offset.$id", null)
    fun saveOffset(id: String, value: String?) {
        if (value.isNullOrBlank()) return
        // Commit the cursor only after the encrypted update queue is durably committed.
        check(prefs.edit().putString("offset.$id", value).commit()) { "ذخیره cursor روبیکا ناموفق بود." }
    }

    private fun readPending(id: String): org.json.JSONArray {
        val stored = prefs.getString("pending.$id", null) ?: return org.json.JSONArray()
        return runCatching {
            val encoded = if (stored.startsWith("enc:")) secretStore.decrypt(stored.removePrefix("enc:")) else "[]"
            org.json.JSONArray(encoded)
        }.getOrDefault(org.json.JSONArray())
    }

    @Synchronized
    fun enqueueUpdates(id: String, incoming: org.json.JSONArray) {
        val existing = readPending(id)
        val merged = org.json.JSONArray()
        for (i in 0 until existing.length()) merged.put(existing.get(i))
        for (i in 0 until incoming.length()) {
            val item = incoming.get(i)
            val signature = item.toString()
            var found = false
            for (j in 0 until merged.length()) if (merged.get(j).toString() == signature) { found = true; break }
            if (!found) merged.put(item)
        }
        // Keep the persistent queue bounded by both item count and encoded size.
        var start = (merged.length() - 50).coerceAtLeast(0)
        var encoded = "[]"
        while (start < merged.length()) {
            val bounded = org.json.JSONArray()
            for (i in start until merged.length()) bounded.put(merged.get(i))
            encoded = bounded.toString()
            if (encoded.length <= 200_000) break
            start += 1
        }
        if (encoded.length > 200_000) encoded = "[]" // A single oversized update is dropped safely.
        // Message content can be private too; encrypt it at rest with the Keystore key.
        val encrypted = "enc:" + secretStore.encrypt(encoded)
        check(prefs.edit().putString("pending.$id", encrypted).commit()) {
            "ذخیره امن پیام‌های دریافتی ناموفق بود."
        }
    }

    @Synchronized
    fun drainUpdates(id: String): org.json.JSONArray {
        val value = readPending(id)
        check(prefs.edit().remove("pending.$id").commit()) {
            "پاک‌سازی صف پیام‌ها ناموفق بود."
        }
        return value
    }

    fun pendingBotIds(): List<String> = prefs.all.keys.asSequence()
        .filter { it.startsWith("pending.") }
        .map { it.removePrefix("pending.") }
        .toList()

    fun list(): List<BotRecord> = prefs.all.keys.asSequence()
        .filter { it.startsWith("label.") }
        .mapNotNull { key ->
            val id = key.removePrefix("label.")
            prefs.getString(key, null)?.let { BotRecord(id, it) }
        }.toList()

    fun remove(id: String) {
        prefs.edit().remove("token.$id").remove("label.$id").remove("offset.$id").remove("pending.$id").apply()
    }

    fun removeAll() {
        prefs.edit().clear().commit()
        secretStore.deleteKey()
    }

    fun setPollingWanted(wanted: Boolean) {
        prefs.edit().putBoolean("polling_wanted", wanted).apply()
    }

    fun isPollingWanted(): Boolean = prefs.getBoolean("polling_wanted", false)

    fun publicJson(): String = JSONObject().put("bots", list().map {
        JSONObject().put("id", it.id).put("label", it.label)
    }).toString()
}
