import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// The desktop app's version (quire/__init__.py) is the single source of truth.
val desktopVersion: String = Regex("""__version__ = "(.+?)"""")
    .find(rootDir.resolve("../quire/__init__.py").readText())!!.groupValues[1]
val versionParts = desktopVersion.split(".").map { it.toInt() }

// Release signing: from environment variables in CI, or keystore.properties locally.
val signing = Properties().apply {
    rootDir.resolve("keystore.properties").takeIf { it.exists() }?.inputStream()?.use(::load)
}
fun secret(name: String): String? = System.getenv(name) ?: signing.getProperty(name)

android {
    namespace = "io.github.quezka.quire"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.quezka.quire"
        minSdk = 26
        targetSdk = 35
        versionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]
        versionName = desktopVersion
        // Phones only (Tesseract ships native code per ABI); keeps the APK small.
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    signingConfigs {
        create("release") {
            val store = secret("QUIRE_KEYSTORE")
            if (store != null) {
                storeFile = file(store)
                storePassword = secret("QUIRE_KEYSTORE_PASSWORD")
                keyAlias = secret("QUIRE_KEY_ALIAS") ?: "quire"
                keyPassword = secret("QUIRE_KEY_PASSWORD") ?: secret("QUIRE_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (secret("QUIRE_KEYSTORE") != null) signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    androidResources { noCompress += "traineddata" }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
        unitTests.isIncludeAndroidResources = true
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("androidx.core:core-ktx:1.15.0")
    // The home-screen agenda widget (Apache-2.0).
    implementation("androidx.glance:glance-appwidget:1.1.1")
    implementation("androidx.glance:glance-material3:1.1.1")
    // Scanning the computer's "set up your phone" QR code (Apache-2.0).
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    // Reading printed handouts into notes, offline (Apache-2.0; models in assets/tessdata).
    implementation("cz.adaptech.tesseract4android:tesseract4android:4.7.0")
    implementation("androidx.exifinterface:exifinterface:1.3.7")
    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
    // Rendering screens on the JVM for screenshot checks (no device needed).
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}
