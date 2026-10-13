package io.github.quezka.quire.sync

import io.github.quezka.quire.data.SyncRecord

/**
 * Sends each call to the adapter for `config.backend`, so a phone can move from Firebase to a
 * Quire server without the sync engine knowing which is which (the desktop's RoutingCloud).
 */
class RoutingCloud(
    private val firebase: Cloud = FirebaseCloud(),
    private val server: Cloud = QuireServerCloud(),
) : Cloud {
    private fun of(config: CloudConfig) = if (config.backend == Backends.SERVER) server else firebase

    override fun signUp(config: CloudConfig, email: String, password: String, invite: String) =
        of(config).signUp(config, email, password, invite)

    override fun signIn(config: CloudConfig, email: String, password: String) =
        of(config).signIn(config, email, password)

    override fun refresh(config: CloudConfig, refreshToken: String) =
        of(config).refresh(config, refreshToken)

    override fun pull(config: CloudConfig, session: CloudSession, cursor: String?): Pair<List<SyncRecord>, String?> =
        of(config).pull(config, session, cursor)

    override fun push(config: CloudConfig, session: CloudSession, records: List<SyncRecord>) =
        of(config).push(config, session, records)
}
