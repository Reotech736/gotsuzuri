package io.github.reotech736.gotsuzuri

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize()) { CameraScreen() }
            }
        }
    }
}

@Composable
private fun CameraScreen() {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    fun cameraAllowed() = ContextCompat.checkSelfPermission(
        context, Manifest.permission.CAMERA
    ) == PackageManager.PERMISSION_GRANTED

    var allowed by remember { mutableStateOf(cameraAllowed()) }
    var message by rememberSaveable { mutableStateOf("カメラを許可すると撮影できます。") }
    var savedUri by rememberSaveable { mutableStateOf<String?>(null) }
    var capture by remember { mutableStateOf<ImageCapture?>(null) }
    var saving by remember { mutableStateOf(false) }
    var retry by remember { mutableIntStateOf(0) }
    val executor = remember(context) { ContextCompat.getMainExecutor(context) }
    val previewView = remember(context) {
        PreviewView(context).apply {
            // TextureViewを使い、Composeとの重ね合わせを安定させる。
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FIT_CENTER
        }
    }
    val permissionRequest = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        allowed = granted
        message = if (granted) "カメラを準備しています。" else
            "カメラが許可されていません。再度許可するか、アプリ設定でカメラを許可してください。"
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) allowed = cameraAllowed()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    DisposableEffect(allowed, lifecycleOwner, previewView, retry) {
        var disposed = false
        var provider: ProcessCameraProvider? = null
        val preview = Preview.Builder().build()
        val photo = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .build()
        capture = null
        if (allowed) {
            message = "カメラを準備しています。"
            val future = ProcessCameraProvider.getInstance(context)
            future.addListener({
                if (!disposed) {
                    try {
                        val cameraProvider = future.get()
                        provider = cameraProvider
                        preview.setSurfaceProvider(previewView.surfaceProvider)
                        cameraProvider.bindToLifecycle(
                            lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, photo
                        )
                        capture = photo
                        message = "撮影できます。"
                    } catch (_: Exception) {
                        message = "カメラを開始できません。他のカメラアプリを閉じて再試行してください。"
                    }
                }
            }, executor)
        }
        onDispose {
            disposed = true
            capture = null
            provider?.unbind(preview, photo)
        }
    }

    Column(
        Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("碁つづり", style = MaterialTheme.typography.headlineMedium)
        Text("カメラ動作確認 · 写真は Pictures/Gotsuzuri に保存")
        if (allowed) {
            AndroidView(
                factory = { previewView },
                modifier = Modifier.fillMaxWidth().weight(1f)
            )
        } else {
            Text("碁盤が映るようにスマホを固定してください。", Modifier.weight(1f))
            Button(onClick = { permissionRequest.launch(Manifest.permission.CAMERA) }) {
                Text("カメラを許可")
            }
            TextButton(onClick = {
                context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:${context.packageName}")))
            }) { Text("アプリ設定を開く") }
        }
        Text(message)
        if (allowed) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(enabled = capture != null && !saving, onClick = {
                    val photo = capture ?: return@Button
                    saving = true
                    message = "保存しています。"
                    photo.targetRotation = previewView.display?.rotation ?: android.view.Surface.ROTATION_0
                    val stamp = SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US).format(Date())
                    val name = "Gotsuzuri_${stamp}_${UUID.randomUUID().toString().take(8)}.jpg"
                    val values = ContentValues().apply {
                        put(MediaStore.Images.Media.DISPLAY_NAME, name)
                        put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                        put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Gotsuzuri")
                    }
                    val options = ImageCapture.OutputFileOptions.Builder(
                        context.contentResolver, MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values
                    ).build()
                    try {
                        photo.takePicture(options, executor, object : ImageCapture.OnImageSavedCallback {
                            override fun onImageSaved(result: ImageCapture.OutputFileResults) {
                                saving = false
                                savedUri = result.savedUri?.toString()
                                message = "保存しました: $name"
                            }
                            override fun onError(exception: ImageCaptureException) {
                                saving = false
                                message = "保存できませんでした。空き容量とカメラの状態を確認して再撮影してください。"
                            }
                        })
                    } catch (_: Exception) {
                        saving = false
                        message = "撮影できませんでした。カメラの許可と空き容量を確認してください。"
                    }
                }) { Text(if (saving) "保存中…" else "写真を保存") }
                if (capture == null) {
                    TextButton(onClick = { retry++ }) { Text("再試行") }
                }
            }
        }
        savedUri?.let { uri ->
            TextButton(onClick = {
                try {
                    context.startActivity(Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(Uri.parse(uri), "image/jpeg")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    })
                } catch (_: ActivityNotFoundException) {
                    message = "写真アプリがありません。ファイル管理から Pictures/Gotsuzuri を開いてください。"
                } catch (_: SecurityException) {
                    message = "写真を開けません。ギャラリーで Pictures/Gotsuzuri を確認してください。"
                }
            }) { Text("保存した写真を開く") }
        }
    }
}
