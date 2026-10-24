package io.github.reotech736.gotsuzuri

import android.graphics.ImageDecoder
import android.graphics.Paint
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.max
import kotlin.math.roundToInt

private data class PhotoLoad(val image: ImageBitmap? = null, val failed: Boolean = false)
private data class PhotoAnalysis(
    val corners: List<ImagePoint>,
    val result: StoneAnalysis? = null,
    val failed: Boolean = false
)

@Composable
fun BoardPhotoScreen(uri: String, onReturnToCamera: () -> Unit) {
    val resolver = LocalContext.current.contentResolver
    var reload by remember { mutableIntStateOf(0) }
    val photo by produceState(PhotoLoad(), uri, reload) {
        value = PhotoLoad()
        value = withContext(Dispatchers.IO) {
            try {
                val source = ImageDecoder.createSource(resolver, uri.toUri())
                val bitmap = ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
                    // JPEGの向きはImageDecoderで補正。表示用だけ縮小し、保存JPEGは変更しない。
                    val scale = minOf(1.0, 2048.0 / max(info.size.width, info.size.height))
                    decoder.setTargetSize(
                        max(1, (info.size.width * scale).roundToInt()),
                        max(1, (info.size.height * scale).roundToInt())
                    )
                    decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                }
                PhotoLoad(image = bitmap.asImageBitmap())
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                PhotoLoad(failed = true)
            }
        }
    }
    var coordinates by rememberSaveable(uri) { mutableStateOf(doubleArrayOf()) }
    val corners = coordinates.asList().chunked(2).map { ImagePoint(it[0], it[1]) }
    val projection = remember(corners) { BoardProjection.fromCorners(corners) }
    var analysisRun by rememberSaveable(uri) { mutableIntStateOf(0) }
    val analysis by produceState<PhotoAnalysis?>(null, photo.image, corners, analysisRun) {
        value = null
        val image = photo.image
        if (analysisRun > 0 && image != null && projection != null) {
            value = withContext(Dispatchers.Default) {
                try {
                    val pixels = IntArray(image.width * image.height)
                    image.asAndroidBitmap().getPixels(pixels, 0, image.width, 0, 0, image.width, image.height)
                    PhotoAnalysis(corners, StoneClassifier.analyze(PixelImage(image.width, image.height, pixels), projection))
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    PhotoAnalysis(corners, failed = true)
                }
            }
        }
    }
    val currentAnalysis = analysis?.takeIf { analysisRun > 0 && it.corners == corners }
    val result = currentAnalysis?.result
    val cornerNames = listOf("左上", "右上", "右下", "左下")
    BackHandler(onBack = onReturnToCamera)

    Column(
        Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text("碁盤の四隅を指定", style = MaterialTheme.typography.titleLarge)
        Text("写真を保存しました。左上→右上→右下→左下の順に指定します。")
        Text("盤の木枠ではなく、最外周の交点を指定してください。")
        val image = photo.image
        if (image != null) {
            val instruction = when {
                corners.size < 4 -> "${corners.size + 1}/4：${cornerNames[corners.size]}の交点をタップ"
                projection == null -> "四隅が交差・重複しています。位置を調整するか、指定し直してください。"
                else -> "19×19交点を表示中。四隅の丸をドラッグして調整できます。"
            }
            Text(instruction, color = if (corners.size == 4 && projection == null) {
                MaterialTheme.colorScheme.error
            } else MaterialTheme.colorScheme.onSurface)
            BoardImage(
                image, corners, projection,
                onCornersChange = { points ->
                    analysisRun = 0
                    coordinates = points.flatMap { listOf(it.x, it.y) }.toDoubleArray()
                },
                analysis = result,
                modifier = Modifier.fillMaxWidth().weight(1f)
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(enabled = corners.isNotEmpty(), onClick = {
                    analysisRun = 0
                    coordinates = coordinates.dropLast(2).toDoubleArray()
                }) { Text("1点戻す") }
                TextButton(enabled = corners.isNotEmpty(), onClick = { analysisRun = 0; coordinates = doubleArrayOf() }) {
                    Text("すべてやり直す")
                }
            }
            if (result != null) {
                Text("試験候補：黒${result.count(IntersectionState.BLACK)}・白${result.count(IntersectionState.WHITE)}・空${result.count(IntersectionState.EMPTY)}・不明${result.count(IntersectionState.UNKNOWN)}")
                Text("黒白の丸＝石候補、細線＝対応する交点、緑点＝空、橙の輪＝不明。")
                Text(result.note, style = MaterialTheme.typography.bodySmall)
            } else if (currentAnalysis?.failed == true) {
                Text("石の試験判定に失敗しました。もう一度お試しください。", color = MaterialTheme.colorScheme.error)
            } else if (analysisRun > 0) {
                Text("石の配置を試験判定しています。")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(enabled = projection != null && (analysisRun == 0 || currentAnalysis != null), onClick = { analysisRun++ }) {
                    Text("石の配置を試験判定")
                }
                if (analysisRun > 0) TextButton(onClick = { analysisRun = 0 }) { Text("交点だけ表示") }
            }
        } else {
            Text(
                if (photo.failed) "写真を読み込めませんでした。再試行するか、撮影に戻ってください。"
                else "写真を読み込んでいます。",
                Modifier.weight(1f)
            )
            if (photo.failed) Button(onClick = { reload++ }) { Text("再読み込み") }
        }
        Button(onClick = onReturnToCamera) { Text("撮影に戻る") }
    }
}

@Composable
private fun BoardImage(
    image: ImageBitmap,
    corners: List<ImagePoint>,
    projection: BoardProjection?,
    onCornersChange: (List<ImagePoint>) -> Unit,
    modifier: Modifier = Modifier,
    analysis: StoneAnalysis? = null
) {
    var viewSize by remember { mutableStateOf(IntSize.Zero) }
    val viewport = remember(image, viewSize) {
        ImageViewport.fit(image.width, image.height, viewSize.width, viewSize.height)
    }
    val latestCorners by rememberUpdatedState(corners)
    val latestChange by rememberUpdatedState(onCornersChange)
    var magnifiedCorner by remember { mutableStateOf<Int?>(null) }
    val labelPaint = remember {
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.BLACK
            textAlign = Paint.Align.CENTER
        }
    }
    Canvas(modifier.onSizeChanged { viewSize = it }
        .semantics { contentDescription = "盤面画像、四隅指定${corners.size}/4、交点${if (projection == null) 0 else 361}個" }
        .pointerInput(viewport) {
            val frame = viewport ?: return@pointerInput
            // ドラッグ開始のしきい値に達する前から、押している隅を見られるようにする。
            // ここではイベントを消費せず、下のタップ・ドラッグ処理へ渡す。
            awaitEachGesture {
                val down = awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
                val current = latestCorners
                magnifiedCorner = if (current.size == 4) current.indices.minByOrNull { index ->
                    val point = frame.toDisplay(current[index])
                    (Offset(point.x.toFloat(), point.y.toFloat()) - down.position).getDistance()
                }?.takeIf { index ->
                    val point = frame.toDisplay(current[index])
                    (Offset(point.x.toFloat(), point.y.toFloat()) - down.position).getDistance() <= 32.dp.toPx()
                } else null
                try {
                    do {
                        val event = awaitPointerEvent(PointerEventPass.Final)
                    } while (event.changes.any { it.pressed })
                } finally {
                    magnifiedCorner = null
                }
            }
        }
        .pointerInput(viewport) {
            val frame = viewport ?: return@pointerInput
            detectTapGestures { position ->
                val current = latestCorners
                if (current.size < 4) {
                    frame.toImage(position.x.toDouble(), position.y.toDouble())?.let {
                        latestChange(current + it)
                    }
                }
            }
        }
        .pointerInput(viewport) {
            val frame = viewport ?: return@pointerInput
            var selected = -1
            detectDragGestures(
                onDragStart = { position ->
                    val current = latestCorners
                    selected = if (current.size == 4) current.indices.minByOrNull { index ->
                        val point = frame.toDisplay(current[index])
                        (Offset(point.x.toFloat(), point.y.toFloat()) - position).getDistance()
                    }?.takeIf { index ->
                        val point = frame.toDisplay(current[index])
                        (Offset(point.x.toFloat(), point.y.toFloat()) - position).getDistance() <= 32.dp.toPx()
                    } ?: -1 else -1
                },
                onDragEnd = { selected = -1 },
                onDragCancel = { selected = -1 }
            ) { change, amount ->
                val current = latestCorners
                if (selected in current.indices) {
                    change.consume()
                    val point = current[selected]
                    latestChange(current.toMutableList().apply {
                        this[selected] = ImagePoint(
                            (point.x + amount.x / frame.width).coerceIn(0.0, 1.0),
                            (point.y + amount.y / frame.height).coerceIn(0.0, 1.0)
                        )
                    })
                }
            }
        }
    ) {
        drawRect(Color.Black)
        val frame = viewport ?: return@Canvas
        drawImage(
            image,
            dstOffset = IntOffset(frame.left.roundToInt(), frame.top.roundToInt()),
            dstSize = IntSize(frame.width.roundToInt(), frame.height.roundToInt())
        )
        fun display(point: ImagePoint): Offset {
            val mapped = frame.toDisplay(point)
            return Offset(mapped.x.toFloat(), mapped.y.toFloat())
        }
        if (projection != null) {
            for (row in 0..18) for (column in 0..18) {
                val position = display(projection.intersection(column, row))
                val candidate = analysis?.candidates?.get(row * 19 + column)
                val state = candidate?.state
                when (state) {
                    IntersectionState.BLACK, IntersectionState.WHITE -> {
                        val fill = if (state == IntersectionState.BLACK) Color.Black else Color.White
                        val stonePosition = candidate.stoneCenter?.let(::display) ?: position
                        drawLine(Color.Cyan, position, stonePosition, 1.dp.toPx())
                        drawCircle(Color.Cyan, 1.5.dp.toPx(), position)
                        drawCircle(fill, 4.dp.toPx(), stonePosition)
                        drawCircle(if (state == IntersectionState.BLACK) Color.White else Color.Black,
                            4.dp.toPx(), stonePosition, style = Stroke(1.dp.toPx()))
                    }
                    IntersectionState.UNKNOWN -> drawCircle(Color(0xFFFF9800), 3.dp.toPx(), position, style = Stroke(1.5.dp.toPx()))
                    else -> {
                        drawCircle(Color.Black, 3.dp.toPx(), position)
                        drawCircle(if (state == IntersectionState.EMPTY) Color.Green else Color.Cyan, 1.8.dp.toPx(), position)
                    }
                }
            }
        }
        corners.forEachIndexed { index, point ->
            val position = display(point)
            drawCircle(Color(0xFFFFC107), 12.dp.toPx(), position)
            drawCircle(Color.Black, 12.dp.toPx(), position, style = Stroke(2.dp.toPx()))
            labelPaint.textSize = 14.dp.toPx()
            drawContext.canvas.nativeCanvas.drawText(
                "${index + 1}", position.x, position.y - (labelPaint.ascent() + labelPaint.descent()) / 2,
                labelPaint
            )
        }
        magnifiedCorner?.let { index -> corners.getOrNull(index) }?.let { point ->
            val source = display(point)
            val margin = 4.dp.toPx()
            val lensWidth = minOf(152.dp.toPx(), size.width - margin * 2)
            val lensHeight = minOf(112.dp.toPx(), size.height - margin * 2)
            if (lensWidth <= 0 || lensHeight <= 0) return@let
            val halfWidth = lensWidth / 2
            val halfHeight = lensHeight / 2
            val gap = 36.dp.toPx()
            val above = source.y - halfHeight - gap
            val center = Offset(
                source.x.coerceIn(halfWidth + margin, size.width - halfWidth - margin),
                (if (above - halfHeight >= margin) above else source.y + halfHeight + gap)
                    .coerceIn(halfHeight + margin, size.height - halfHeight - margin)
            )
            val left = center.x - halfWidth
            val top = center.y - halfHeight
            drawRect(Color.Black, Offset(left, top), Size(lensWidth, lensHeight))
            clipRect(left, top, left + lensWidth, top + lensHeight) {
                withTransform({
                    translate(center.x - source.x * 3f, center.y - source.y * 3f)
                    scale(3f, 3f, pivot = Offset.Zero)
                }) {
                    // 元画像だけを拡大し、黄色い操作ハンドルで交点を覆わない。
                    drawImage(
                        image,
                        dstOffset = IntOffset(frame.left.roundToInt(), frame.top.roundToInt()),
                        dstSize = IntSize(frame.width.roundToInt(), frame.height.roundToInt())
                    )
                }
            }
            drawRect(Color.White, Offset(left, top), Size(lensWidth, lensHeight), style = Stroke(2.dp.toPx()))
            // 中央を空けた十字で対象の位置を示し、実際の線を見えるままにする。
            for (direction in listOf(Offset(1f, 0f), Offset(-1f, 0f), Offset(0f, 1f), Offset(0f, -1f))) {
                val start = center + direction * 4.dp.toPx()
                val end = center + direction * 14.dp.toPx()
                drawLine(Color.Black, start, end, 3.dp.toPx())
                drawLine(Color.White, start, end, 1.dp.toPx())
            }
        }
    }
}
