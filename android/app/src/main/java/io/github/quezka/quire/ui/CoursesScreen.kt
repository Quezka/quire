package io.github.quezka.quire.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.material3.Text
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Repository

/** Courses and their class times: the timetable behind Today and Week. */
@Composable
fun CoursesScreen(repo: Repository, version: Int, back: () -> Unit) {
    val courses = remember(version) { repo.courses() }
    var editing by remember { mutableStateOf<String?>(null) }
    var creating by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            PageBar(stringResource(R.string.nav_courses), back)
            if (courses.isEmpty()) Box(Modifier.padding(16.dp)) { Hint(stringResource(R.string.no_courses)) }
            LazyColumn(contentPadding = PaddingValues(16.dp, 0.dp, 16.dp, 96.dp)) {
                items(courses, key = { it.uid }) { c ->
                    Row(Modifier.fillMaxWidth().animateItem().clickable { editing = c.uid }.padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(14.dp).background(parseColor(c.color), CircleShape))
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(c.name, fontWeight = FontWeight.SemiBold)
                            val meta = listOfNotNull(c.teacher.ifBlank { null },
                                pluralStringResource(R.plurals.classes_a_week, c.slots.size, c.slots.size))
                            Hint(meta.joinToString(" · "))
                        }
                    }
                }
            }
        }
        FloatingActionButton(onClick = { creating = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp)) {
            Icon(Icons.Filled.Add, stringResource(R.string.new_course))
        }
    }
    if (creating) CourseEditor(repo, null) { creating = false }
    editing?.let { CourseEditor(repo, it) { editing = null } }
}
