package io.github.quezka.quire.ocr

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import com.googlecode.tesseract.android.TessBaseAPI
import io.github.quezka.quire.domain.Markdown
import java.io.File

/**
 * Reads printed text from a photo, offline, with Tesseract (Italian and English models
 * in assets/tessdata). Slow-ish (a few seconds): call off the main thread.
 */
class Ocr(private val context: Context) {
    companion object {
        const val LANGUAGES = "ita+eng"
        private const val MAX_SIDE = 2400 // enough for print; more only costs time
    }

    /** Tesseract reads its models from files: copy them out of the APK once. */
    private fun dataDir(): File {
        val root = File(context.noBackupFilesDir, "ocr")
        val dir = File(root, "tessdata").apply { mkdirs() }
        for (lang in LANGUAGES.split("+")) {
            val target = File(dir, "$lang.traineddata")
            if (!target.exists() || target.length() == 0L) {
                context.assets.open("tessdata/$lang.traineddata").use { input ->
                    target.outputStream().use { input.copyTo(it) }
                }
            }
        }
        return root
    }

    fun read(uri: Uri): String {
        val bitmap = load(uri) ?: throw OcrException("Couldn't open that picture.")
        val api = TessBaseAPI()
        try {
            if (!api.init(dataDir().absolutePath, LANGUAGES)) throw OcrException("The text reader didn't start.")
            api.pageSegMode = TessBaseAPI.PageSegMode.PSM_AUTO
            api.setImage(bitmap)
            val text = api.utF8Text.orEmpty()
            return Markdown.tidyOcr(text)
        } finally {
            api.recycle()
            bitmap.recycle()
        }
    }

    /** The picture, upright (camera photos carry their rotation in EXIF) and scaled down. */
    private fun load(uri: Uri): Bitmap? {
        val resolver = context.contentResolver
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        if (bounds.outWidth <= 0) return null
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_SIDE) sample *= 2
        val bitmap = resolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: return null
        val rotation = resolver.openInputStream(uri)?.use {
            when (ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
                ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                else -> 0f
            }
        } ?: 0f
        if (rotation == 0f) return bitmap
        val upright = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height,
            Matrix().apply { postRotate(rotation) }, true)
        if (upright != bitmap) bitmap.recycle()
        return upright
    }
}

class OcrException(message: String) : Exception(message)
