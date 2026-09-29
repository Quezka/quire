package io.github.quezka.quire.ui

import android.content.Intent
import android.os.Build
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import io.github.quezka.quire.BuildConfig
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.notify.ReminderSettings
import io.github.quezka.quire.sync.CloudConfig
import io.github.quezka.quire.sync.DeviceLink
import io.github.quezka.quire.sync.SyncEngine
import io.github.quezka.quire.sync.SyncManager
import io.github.quezka.quire.update.Release
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

@Composable
fun SettingsScreen(container: Container, back: () -> Unit) {
    val sync = container.sync
    val state by sync.state.collectAsState()
    val status = state.status
    val context = LocalContext.current
    var signingOut by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        PageBar(stringResource(R.string.nav_settings), back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Panel(stringResource(R.string.sync), Modifier.animateContentSize(Motion.gentle())) {
                if (status.setUp) {
                    Text(stringResource(R.string.signed_in_as, status.email))
                    val last = status.lastSync?.atZone(ZoneId.systemDefault())?.format(
                        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT).withLocale(Locale.getDefault()))
                    Hint(last?.let { stringResource(R.string.last_synced, it) } ?: stringResource(R.string.never_synced))
                    if (status.pending > 0) Hint(pluralStringResource(R.plurals.changes_waiting, status.pending, status.pending))
                    if (status.problem.isNotEmpty()) Text(syncMessage(context, status.problem),
                        color = MaterialTheme.colorScheme.error)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = sync::syncNow, enabled = !state.running) {
                            Text(stringResource(if (state.running) R.string.syncing else R.string.sync_now))
                        }
                        OutlinedButton(onClick = { signingOut = true }) { Text(stringResource(R.string.sign_out)) }
                    }
                } else {
                    if (status.problem.isNotEmpty()) Text(syncMessage(context, status.problem),
                        color = MaterialTheme.colorScheme.error)
                    LinkSetup(container)
                    SyncSetup(sync, status.projectId, status.email)
                }
            }
            RemindersPanel(container)
            UpdatesPanel(container)
            CurrencyPanel(container)
            Panel(stringResource(R.string.about)) {
                Text(stringResource(R.string.version, BuildConfig.VERSION_NAME))
                Hint(stringResource(R.string.licence))
                val uri = LocalUriHandler.current
                TextButton(onClick = { uri.openUri("https://github.com/Quezka/quire") }) {
                    Text(stringResource(R.string.source_code))
                }
            }
        }
    }
    if (signingOut) ConfirmDialog(stringResource(R.string.sign_out_question),
        stringResource(R.string.sign_out), onConfirm = { sync.disconnect(); signingOut = false },
        onDismiss = { signingOut = false })
}

/** Scan the QR code the computer shows (Settings → Sync → Set up your phone). */
@Composable
private fun LinkSetup(container: Container) {
    val context = LocalContext.current
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    fun use(text: String?) {
        if (text == null) return
        val link = DeviceLink.parse(text)
        if (link == null) { error = context.getString(R.string.not_a_quire_code); return }
        busy = true; error = null
        container.sync.connectWithLink(link) { failure ->
            if (failure != null) { busy = false; error = syncMessage(context, failure.message); return@connectWithLink }
            val user = link.registerUser
            val password = link.registerPassword
            if (user != null && password != null) scope.launch {
                runCatching { withContext(Dispatchers.IO) { container.school.connect(user, password); container.syncSchool() } }
                busy = false
            } else busy = false
        }
    }
    val scanner = rememberLauncherForActivityResult(ScanContract()) { use(it.contents) }
    Hint(stringResource(R.string.link_help))
    Button(enabled = !busy, onClick = {
        scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            .setPrompt(context.getString(R.string.scan_prompt)).setBeepEnabled(false).setOrientationLocked(false))
    }) {
        Icon(Icons.Filled.QrCodeScanner, null)
        Text("  " + stringResource(if (busy) R.string.connecting else R.string.scan_code))
    }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    Hint(stringResource(R.string.or_by_hand))
}

@Composable
private fun SyncSetup(sync: SyncManager, project: String, email: String) {
    val context = LocalContext.current
    var projectId by rememberSaveable { mutableStateOf(project) }
    var apiKey by rememberSaveable { mutableStateOf("") }
    var mail by rememberSaveable { mutableStateOf(email) }
    var password by rememberSaveable { mutableStateOf("") }
    var create by rememberSaveable { mutableStateOf(false) }
    var takeCloud by rememberSaveable { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Hint(stringResource(R.string.sync_off))
    Hint(stringResource(R.string.sync_help))
    OutlinedTextField(projectId, { projectId = it }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text(stringResource(R.string.project_id)) })
    OutlinedTextField(apiKey, { apiKey = it }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text(stringResource(R.string.api_key)) })
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        SegmentedButton(selected = !create, onClick = { create = false },
            shape = SegmentedButtonDefaults.itemShape(0, 2)) { Text(stringResource(R.string.existing_account)) }
        SegmentedButton(selected = create, onClick = { create = true },
            shape = SegmentedButtonDefaults.itemShape(1, 2)) { Text(stringResource(R.string.new_account)) }
    }
    OutlinedTextField(mail, { mail = it }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text(stringResource(R.string.email)) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
    OutlinedTextField(password, { password = it }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text(stringResource(R.string.password)) },
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
    AnimatedVisibility(!create) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(takeCloud, { takeCloud = it })
            Text(stringResource(R.string.take_cloud_copy))
        }
    }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    Button(enabled = !busy, onClick = {
        val problem = SyncEngine.check(projectId, apiKey, mail, password)
        if (problem != null) { error = syncMessage(context, problem); return@Button }
        busy = true; error = null
        sync.connect(CloudConfig(projectId.trim(), apiKey.trim()), mail, password, create,
            takeCloudCopy = !create && takeCloud) { failure ->
            busy = false
            error = failure?.let { syncMessage(context, it.message) }
        }
    }) { Text(stringResource(if (busy) R.string.connecting else R.string.connect)) }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun RemindersPanel(container: Container) {
    val context = LocalContext.current
    var settings by remember { mutableStateOf(container.reminders.settings()) }
    var allowed by remember { mutableStateOf(container.notifier.allowed()) }
    fun save(new: ReminderSettings) { settings = new; container.reminders.save(new) }
    LaunchedEffect(Unit) { allowed = container.notifier.allowed() }
    Panel(stringResource(R.string.reminders)) {
        if (!allowed) {
            Text(stringResource(R.string.notifications_off), color = MaterialTheme.colorScheme.error)
            OutlinedButton(onClick = {
                context.startActivity(Intent(AndroidSettings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(AndroidSettings.EXTRA_APP_PACKAGE, context.packageName))
            }) { Text(stringResource(R.string.allow_notifications)) }
        }
        Hint(stringResource(R.string.remind_me))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (choice in ReminderSettings.CHOICES) FilterChip(settings.minutesBefore == choice,
                { save(settings.copy(minutesBefore = choice)) },
                label = { Text(when (choice) {
                    null -> stringResource(R.string.off)
                    0 -> stringResource(R.string.at_start)
                    else -> stringResource(R.string.minutes_before, choice)
                }) })
        }
        AnimatedVisibility(settings.minutesBefore != null) {
            Column {
                for ((label, value, set) in listOf(
                    Triple(R.string.for_events, settings.events) { v: Boolean -> settings.copy(events = v) },
                    Triple(R.string.for_classes, settings.classes) { v: Boolean -> settings.copy(classes = v) },
                    Triple(R.string.for_shifts, settings.shifts) { v: Boolean -> settings.copy(shifts = v) },
                )) Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(label), Modifier.weight(1f))
                    Switch(value, { save(set(it)) })
                }
            }
        }
        if (Build.VERSION.SDK_INT >= 31 && !context.getSystemService(android.app.AlarmManager::class.java).canScheduleExactAlarms()) {
            Hint(stringResource(R.string.exact_alarms_off))
            TextButton(onClick = {
                context.startActivity(Intent(AndroidSettings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                    android.net.Uri.parse("package:" + context.packageName)))
            }) { Text(stringResource(R.string.allow_exact_alarms)) }
        }
    }
}

@Composable
private fun UpdatesPanel(container: Container) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var checking by remember { mutableStateOf(false) }
    var release by remember { mutableStateOf<Release?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    var progress by remember { mutableFloatStateOf(-1f) }
    Panel(stringResource(R.string.updates), Modifier.animateContentSize(Motion.gentle())) {
        val found = release
        if (found == null) {
            Button(enabled = !checking, onClick = {
                checking = true; message = null
                scope.launch {
                    val result = runCatching { withContext(Dispatchers.IO) { container.updater.check() } }
                    checking = false
                    result.onSuccess { release = it; if (it == null) message = context.getString(R.string.up_to_date) }
                        .onFailure { message = it.message }
                }
            }) { Text(stringResource(if (checking) R.string.checking else R.string.check_for_updates)) }
        } else {
            Text(stringResource(R.string.update_available, found.version))
            if (progress >= 0) LinearProgressIndicator({ progress }, Modifier.fillMaxWidth())
            Button(enabled = progress < 0, onClick = {
                progress = 0f
                scope.launch {
                    val result = runCatching {
                        withContext(Dispatchers.IO) { container.updater.install(found) { p -> progress = p } }
                    }
                    progress = -1f
                    result.onFailure { message = it.message }
                }
            }) { Text(stringResource(R.string.download_and_install)) }
        }
        message?.let { Hint(it) }
    }
}

@Composable
private fun CurrencyPanel(container: Container) {
    var code by remember { mutableStateOf(container.settings.get("currency") ?: "EUR") }
    var shown by remember { mutableIntStateOf(0) }
    Panel(stringResource(R.string.currency)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (c in listOf("EUR", "USD", "GBP", "CHF", "RUB")) FilterChip(code == c, {
                code = c; container.settings.set("currency", c); currencyCode = c; shown++
            }, label = { Text(c) })
        }
        Hint(stringResource(R.string.currency_example, money(12.5)).let { if (shown >= 0) it else it })
    }
}
