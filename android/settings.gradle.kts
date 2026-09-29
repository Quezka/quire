pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // Only for Tesseract (OCR), which is published on JitPack.
        maven("https://jitpack.io") { content { includeGroupByRegex("cz\\.adaptech(\\..*)?") } }
    }
}
rootProject.name = "Quire"
include(":app")
