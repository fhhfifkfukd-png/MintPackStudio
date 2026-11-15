plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.mintpack.runtime"
    compileSdk = 36

    defaultConfig {
        applicationId = providers.gradleProperty("mintpackPackageName").orElse("com.mintpack.studio").get()
        minSdk = 24
        targetSdk = providers.gradleProperty("mintpackTargetSdk").orElse("36").get().toInt()
        versionCode = providers.gradleProperty("mintpackVersionCode").orElse("1").get().toInt()
        versionName = providers.gradleProperty("mintpackVersionName").orElse("0.1.0").get()
    }

    buildFeatures { buildConfig = true }

    signingConfigs {
        create("customerRelease") {
            val path = System.getenv("MINTPACK_KEYSTORE_FILE")
            val storePass = System.getenv("MINTPACK_STORE_PASSWORD")
            val alias = System.getenv("MINTPACK_KEY_ALIAS")
            val keyPass = System.getenv("MINTPACK_KEY_PASSWORD")
            if (!path.isNullOrBlank()) {
                storeFile = file(path)
                storePassword = storePass
                keyAlias = alias
                keyPassword = keyPass
            }
        }
    }

    buildTypes {
        debug { applicationIdSuffix = ".debug"; versionNameSuffix = "-debug" }
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("customerRelease")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging { resources.excludes += setOf("META-INF/AL2.0", "META-INF/LGPL2.1") }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.webkit:webkit:1.18.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
}
