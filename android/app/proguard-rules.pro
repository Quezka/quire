# kotlinx.serialization: keep generated serializers.
-keepattributes *Annotation*, InnerClasses
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class io.github.quezka.quire.** { kotlinx.serialization.KSerializer serializer(...); }

# Tesseract/Leptonica (OCR): native code binds to these classes and calls back by name.
-keep class com.googlecode.tesseract.android.** { *; }
-keep class com.googlecode.leptonica.android.** { *; }
