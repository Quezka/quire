package io.github.quezka.quire.sync

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import java.util.Base64

/**
 * What the computer's "Set up your phone" QR code carries (see the desktop's
 * SyncService.phone_link): the sync project and sign-in, and, if chosen, the Classeviva
 * login, so the phone is ready without typing anything. It travels screen to camera only.
 */
data class DeviceLink(
    val projectId: String,
    val apiKey: String,
    val email: String,
    val refreshToken: String,
    val registerUser: String? = null,
    val registerPassword: String? = null,
    val backend: String = Backends.FIREBASE, // for SERVER, projectId is the server's address
) {
    companion object {
        const val PREFIX = "quire-link:"

        fun parse(text: String): DeviceLink? = runCatching {
            val body = text.trim().removePrefix(PREFIX).takeIf { text.trim().startsWith(PREFIX) } ?: return null
            val json = String(Base64.getUrlDecoder().decode(body.trimEnd('=')))
            val o = Json.parseToJsonElement(json).jsonObject
            fun s(k: String) = (o[k] as? JsonPrimitive)?.takeIf { it.isString }?.content
            when ((o["v"] as? JsonPrimitive)?.content) {
                // Version 1: a Firebase project. Version 2: a Quire server's address.
                "1" -> DeviceLink(s("project")!!, s("api_key")!!, s("email").orEmpty(), s("refresh")!!,
                    s("cv_user"), s("cv_pass"))
                "2" -> {
                    if (s("backend") != Backends.SERVER) return null
                    DeviceLink(s("url")!!, "", s("email").orEmpty(), s("refresh")!!,
                        s("cv_user"), s("cv_pass"), Backends.SERVER)
                }
                else -> return null
            }
        }.getOrNull()
    }
}
