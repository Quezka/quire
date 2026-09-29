package io.github.quezka.quire.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Class
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.Work
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.animation.togetherWith
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.Page
import io.github.quezka.quire.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MoreScreen(container: Container, open: (Page) -> Unit) {
    val focusVersion by container.focus.changes.collectAsState()
    val school = remember(focusVersion) { container.school.status() }
    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text(stringResource(R.string.nav_more)) })
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            val timer = container.focus.timer
            MoreRow(Icons.Filled.School, stringResource(R.string.nav_school),
                if (school.connected) school.student.ifEmpty { school.username } else stringResource(R.string.school_not_connected)) {
                open(Page.SCHOOL)
            }
            MoreRow(Icons.Filled.Work, stringResource(R.string.nav_work), stringResource(R.string.work_summary_hint)) { open(Page.WORK) }
            MoreRow(Icons.Filled.Timer, stringResource(R.string.nav_focus),
                stringResource(if (timer.running) R.string.focus_running else R.string.focus_hint)) { open(Page.FOCUS) }
            MoreRow(Icons.Filled.Class, stringResource(R.string.nav_courses), stringResource(R.string.courses_hint)) { open(Page.COURSES) }
            MoreRow(Icons.Filled.Settings, stringResource(R.string.nav_settings), stringResource(R.string.settings_hint)) { open(Page.SETTINGS) }
        }
    }
}

@Composable
private fun MoreRow(icon: ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    val source = remember { MutableInteractionSource() }
    Card(Modifier.fillMaxWidth().pressScale(source).clickable(source, null, onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, Modifier.size(26.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.SemiBold)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** The title bar of a page under More, with a way back. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PageBar(title: String, back: () -> Unit, actions: @Composable () -> Unit = {}) {
    TopAppBar(title = { Text(title) }, navigationIcon = {
        IconButton(onClick = back) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) }
    }, actions = { actions() })
}

@Composable
fun Panel(title: String, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

/** A big number with a label, for summaries. */
@Composable
fun StatTile(label: String, value: String, detail: String = "", modifier: Modifier = Modifier,
             color: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.onSurface) {
    Card(modifier, shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.fillMaxWidth().padding(14.dp)) {
            Text(label.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            AnimatedNumber(value, color)
            if (detail.isNotEmpty()) Text(detail, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** Numbers roll to their new value. */
@Composable
fun AnimatedNumber(value: String, color: androidx.compose.ui.graphics.Color) {
    androidx.compose.animation.AnimatedContent(value, transitionSpec = {
        (androidx.compose.animation.slideInVertically { it } + androidx.compose.animation.fadeIn())
            .togetherWith(androidx.compose.animation.slideOutVertically { -it } + androidx.compose.animation.fadeOut())
    }, label = "number") {
        Text(it, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
fun EmptyBox(text: String) = Box(Modifier.padding(vertical = 8.dp)) { Hint(text) }
