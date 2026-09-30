package io.github.quezka.quire.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R

/** A picture from a note, decoded once per picture. */
@Composable
internal fun NotePicture(uid: String, alt: String, image: (String) -> ByteArray?) {
    val bitmap = remember(uid) {
        image(uid)?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }?.asImageBitmap()
    }
    if (bitmap == null) {
        Text(stringResource(R.string.picture_not_here), color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyMedium)
    } else {
        Image(bitmap, alt, Modifier.fillMaxWidth().padding(vertical = 6.dp)
            .background(Color.White, RoundedCornerShape(8.dp)), contentScale = ContentScale.FillWidth)
    }
}
