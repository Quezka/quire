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
) {
    companion object {
        const val PREFIX = "quire-link:"

        fun parse(text: String): DeviceLink? = runCatching {
            val body = text.trim().removePrefix(PREFIX).takeIf { text.trim().startsWith(PREFIX) } ?: return null
            val json = String(Base64.getUrlDecoder().decode(body.trimEnd('=')))
            val o = Json.parseToJsonElement(json).jsonObject
            fun s(k: String) = (o[k] as? JsonPrimitive)?.takeIf { it.isString }?.content
            if ((o["v"] as? JsonPrimitive)?.content != "1") return null
            DeviceLink(s("project")!!, s("api_key")!!, s("email").orEmpty(), s("refresh")!!,
                s("cv_user"), s("cv_pass"))
        }.getOrNull()
    }
}
