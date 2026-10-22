plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "org.herbstleyd.herbstchat"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.herbstleyd.herbstchat"
        minSdk = 26
        targetSdk = 35
        versionCode = 113
        versionName = "1.1.3"
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86", "x86_64") }
    }

    signingConfigs {
        create("release") {
            val ks = System.getenv("HC_KEYSTORE") ?: rootProject.file("herbstchat-release.jks").path
            if (file(ks).exists()) {
                storeFile = file(ks)
                storePassword = System.getenv("HC_KEYSTORE_PASSWORD") ?: ""
                keyAlias = System.getenv("HC_KEY_ALIAS") ?: "herbstchat"
                keyPassword = System.getenv("HC_KEY_PASSWORD") ?: System.getenv("HC_KEYSTORE_PASSWORD") ?: ""
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            val rel = signingConfigs.getByName("release")
            signingConfig = if (rel.storeFile != null) rel else signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
    packaging { jniLibs { useLegacyPackaging = true } }
}

dependencies {
    val bom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(bom)
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.goterl:lazysodium-android:5.1.0@aar")
    implementation("net.java.dev.jna:jna:5.14.0@aar")
}
