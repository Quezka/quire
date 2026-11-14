package io.github.quezka.quire.notify

import android.app.Notification
import android.content.ComponentName
import android.content.Context
import android.provider.Settings as AndroidSettings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import io.github.quezka.quire.container
import io.github.quezka.quire.domain.Assistant
import io.github.quezka.quire.sync.Settings
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long

/**
 * The notification hub: with notification access, other apps' notifications are taken off the screen and held
 * for the digest (or a batch every few hours), so Quire is the only thing that interrupts. Calls, alarms and
 * anything ongoing always pass; each app can be set to pass, hold (the default) or mute.
 */
class Hub(private val context: Context, private val settings: Settings) {
    enum class Rule(val code: String) { PASS("pass"), HOLD("hold"), MUTE("mute");
        companion object { fun of(code: String?) = entries.firstOrNull { it.code == code } } }

    var enabled: Boolean
        get() = settings.get("hub.on") == "1"
        set(on) { settings.set("hub.on", if (on) "1" else "0") }

    /** Hours between batches of held notifications (0: only in the digests). */
    var batchHours: Int
        get() = settings.get("hub.batch")?.toIntOrNull() ?: 0
        set(h) { settings.set("hub.batch", h.toString()) }

    fun access(): Boolean {
        val listeners = AndroidSettings.Secure.getString(context.contentResolver, "enabled_notification_listeners") ?: return false
        return listeners.contains(ComponentName(context, HubListener::class.java).flattenToString())
    }

    fun rule(pkg: String): Rule = Rule.of(settings.get("hub.rule.$pkg")) ?: Rule.HOLD
    fun setRule(pkg: String, rule: Rule) = settings.set("hub.rule.$pkg", rule.code)

    /** Apps seen so far (package to label), for the rules list. */
    fun apps(): List<Pair<String, String>> = (settings.get("hub.apps") ?: "").split("\n").filter { it.contains("\t") }
        .map { it.substringBefore("\t") to it.substringAfter("\t") }.sortedBy { it.second.lowercase() }

    private fun remember(pkg: String, label: String) {
        val apps = apps().toMap().toMutableMap()
        if (apps[pkg] == label) return
        apps[pkg] = label
        settings.set("hub.apps", apps.entries.joinToString("\n") { "${it.key}\t${it.value}" })
    }

    fun held(): List<Assistant.Held> = runCatching {
        Json.parseToJsonElement(settings.get("hub.held") ?: "[]").jsonArray.map {
            val o = it.jsonObject
            Assistant.Held(o["app"]!!.jsonPrimitive.content, o["title"]!!.jsonPrimitive.content,
                o["text"]!!.jsonPrimitive.content, o["at"]!!.jsonPrimitive.long)
        }
    }.getOrDefault(emptyList())

    private fun save(items: List<Assistant.Held>) = settings.set("hub.held", JsonArray(items.takeLast(MAX_HELD).map {
        JsonObject(mapOf("app" to JsonPrimitive(it.app), "title" to JsonPrimitive(it.title),
            "text" to JsonPrimitive(it.text), "at" to JsonPrimitive(it.at)))
    }).toString())

    fun clearHeld() = settings.set("hub.held", "[]")

    /** What to do with a notification just posted: true if Quire took it off the screen. */
    fun take(sbn: StatusBarNotification): Boolean {
        if (!enabled || sbn.packageName == context.packageName || sbn.isOngoing || !sbn.isClearable) return false
        val n = sbn.notification
        if (n.category in ALWAYS_PASS || n.flags and Notification.FLAG_FOREGROUND_SERVICE != 0) return false
        val label = runCatching {
            context.packageManager.getApplicationLabel(context.packageManager.getApplicationInfo(sbn.packageName, 0)).toString()
        }.getOrDefault(sbn.packageName)
        remember(sbn.packageName, label)
        return when (rule(sbn.packageName)) {
            Rule.PASS -> false
            Rule.MUTE -> true
            Rule.HOLD -> {
                if (n.flags and Notification.FLAG_GROUP_SUMMARY == 0) {
                    val title = n.extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
                    val text = n.extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
                    save(held() + Assistant.Held(label, title, text, sbn.postTime))
                }
                true
            }
        }
    }

    companion object {
        const val MAX_HELD = 300
        val ALWAYS_PASS = setOf(Notification.CATEGORY_CALL, Notification.CATEGORY_ALARM,
            Notification.CATEGORY_NAVIGATION, Notification.CATEGORY_TRANSPORT, Notification.CATEGORY_STOPWATCH)
    }
}

/** Android hands every notification here once the user grants notification access to Quire. */
class HubListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val hub = applicationContext.container.hub
        if (hub.take(sbn)) cancelNotification(sbn.key)
    }
}
