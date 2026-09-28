package io.github.quezka.quire.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.BuildConfig
import io.github.quezka.quire.R
import io.github.quezka.quire.sync.CloudConfig
import io.github.quezka.quire.sync.SyncEngine
import io.github.quezka.quire.sync.SyncManager
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(sync: SyncManager) {
    val state by sync.state.collectAsState()
    val status = state.status
    val context = LocalContext.current
    var signingOut by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text(stringResource(R.string.nav_settings)) })
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Panel(stringResource(R.string.sync)) {
                if (status.setUp) {
                    Text(stringResource(R.string.signed_in_as, status.email))
                    val last = status.lastSync?.atZone(ZoneId.systemDefault())?.format(
                        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT).withLocale(Locale.getDefault()))
                    Hint(last?.let { stringResource(R.string.last_synced, it) }
                        ?: stringResource(R.string.never_synced))
                    if (status.pending > 0) Hint(pluralStringResource(R.plurals.changes_waiting,
                        status.pending, status.pending))
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
                    SyncSetup(sync, status.projectId, status.email)
                }
            }
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

@Composable
private fun Panel(title: String, content: @Composable () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
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
    if (!create) Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(takeCloud, { takeCloud = it })
        Text(stringResource(R.string.take_cloud_copy))
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
