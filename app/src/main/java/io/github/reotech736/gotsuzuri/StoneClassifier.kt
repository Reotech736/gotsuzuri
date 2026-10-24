package io.github.reotech736.gotsuzuri

import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

enum class IntersectionState { EMPTY, BLACK, WHITE, UNKNOWN }

data class IntersectionCandidate(
    val column: Int,
    val row: Int,
    val state: IntersectionState,
    val reason: String? = null,
    // 見つけた上面の画像座標。論理交点や四隅を移動する値ではない。
    val stoneCenter: ImagePoint? = null
)

data class StoneAnalysis(val candidates: List<IntersectionCandidate>, val note: String) {
    fun count(state: IntersectionState) = candidates.count { it.state == state }
}

/** AndroidのBitmapを直接参照せず、同じ処理を人工画像で検証する。 */
class PixelImage(val width: Int, val height: Int, private val pixels: IntArray) {
    init {
        require(width > 0 && height > 0 && width.toLong() * height == pixels.size.toLong())
    }

    fun pixel(x: Int, y: Int): Int = pixels[y * width + x]
}

/** 木地の色を基準にした静止画用の試験判定。手や石の遮蔽を復元する処理ではない。 */
object StoneClassifier {
    private data class ColorSample(val luminance: Double, val saturation: Double, val blueRatio: Double)
    private data class Patch(val colors: List<ColorSample>, val enoughPixels: Boolean)
    private data class StoneMatch(val state: IntersectionState, val column: Double, val row: Double, val score: Double)

    fun analyze(image: PixelImage, projection: BoardProjection): StoneAnalysis {
        val patches = (0..18).flatMap { row ->
            (0..18).map { column -> samplePatch(image, projection, column, row) }
        }
        // 暗い線や石を除き、暖色の木地が十分見える写真だけで基準を作る。
        val wood = patches.flatMap { it.colors }.filter {
            it.luminance in 0.12..0.92 && it.saturation in 0.18..0.78 && it.blueRatio in 0.18..0.78
        }
        val allSampleCount = patches.sumOf { it.colors.size }
        val reference = if (wood.size >= max(100, allSampleCount / 5)) ColorSample(
            median(wood.map { it.luminance }), median(wood.map { it.saturation }),
            median(wood.map { it.blueRatio })
        ) else null

        val matches = patches.mapIndexed { index, patch ->
            if (reference == null || !patch.enoughPixels) emptyList() else {
                val column = index % 19
                val row = index / 19
                buildList {
                    // 上下を固定しない。交点間隔の半分より狭い範囲で候補を探す。
                    for (dy in listOf(-0.4, -0.2, 0.0, 0.2, 0.4)) {
                        for (dx in listOf(-0.4, -0.2, 0.0, 0.2, 0.4)) {
                            val x = column + dx
                            val y = row + dy
                            if (x !in 0.0..18.0 || y !in 0.0..18.0) continue
                            val sample = samplePatch(image, projection, x, y)
                            if (!sample.enoughPixels) continue
                            val state = classifyPatch(column, row, sample.colors, reference).state
                            if (state == IntersectionState.BLACK || state == IntersectionState.WHITE) {
                                val support = sample.colors.count { classifyPatch(column, row, listOf(it), reference).state == state }
                                    .toDouble() / sample.colors.size
                                add(StoneMatch(state, x, y, support - hypot(dx, dy) * 0.08))
                            }
                        }
                    }
                }
            }
        }
        val centralStates = patches.mapIndexed { index, patch ->
            if (reference == null || !patch.enoughPixels) IntersectionState.UNKNOWN
            else classifyPatch(index % 19, index / 19, patch.colors, reference).state
        }
        val selected = matches.mapIndexed { index, options ->
            val central = centralStates[index]
            // 交点自体に十分な石の根拠がある場合、周辺の別色の隣石で覆さない。
            if (central == IntersectionState.BLACK || central == IntersectionState.WHITE) {
                options.firstOrNull { it.column == (index % 19).toDouble() && it.row == (index / 19).toDouble() }
            } else {
                options.takeIf { it.map { match -> match.state }.distinct().size == 1 }
                    ?.maxByOrNull { it.score }
            }
        }
        val candidates = patches.mapIndexed { index, patch ->
            val column = index % 19
            val row = index / 19
            val match = selected[index]
            val collision = match != null && selected.withIndex().any { (otherIndex, other) ->
                val distance = if (other == null) Double.POSITIVE_INFINITY
                    else hypot(match.column - other.column, match.row - other.row)
                otherIndex != index && other != null &&
                    ((centralStates[index] !in listOf(IntersectionState.BLACK, IntersectionState.WHITE) &&
                        centralStates[otherIndex] in listOf(IntersectionState.BLACK, IntersectionState.WHITE) && distance < 0.8) ||
                        (distance < 0.45 && other.score >= match.score - 0.2))
            }
            when {
                reference == null -> IntersectionCandidate(column, row, IntersectionState.UNKNOWN, "木地の色を推定できません")
                !patch.enoughPixels -> IntersectionCandidate(column, row, IntersectionState.UNKNOWN, "交点周辺が小さいか画像端です")
                (match == null && matches[index].map { it.state }.distinct().size > 1) || collision ->
                    IntersectionCandidate(column, row, IntersectionState.UNKNOWN, "石の色または隣の交点との対応が曖昧です")
                match != null -> IntersectionCandidate(column, row, match.state,
                    stoneCenter = projection.imagePointAt(match.column, match.row))
                else -> {
                    val central = classifyPatch(column, row, patch.colors, reference)
                    // 中心だけ木地でも、周囲に石の一部がある場合は空と断定しない。
                    val nearbyStone = selected.any { other -> other != null &&
                        hypot(column - other.column, row - other.row) < 0.8 }
                    if (nearbyStone && central.state == IntersectionState.EMPTY) {
                        IntersectionCandidate(column, row, IntersectionState.UNKNOWN, "周囲の石との対応を確認してください")
                    } else central
                }
            }
        }
        val note = if (reference == null) "木地の色を十分に推定できないため、すべて不明としました。"
        else "交点周辺の石候補を探す試験判定です。影・反射・隠れや大きなずれで誤るため、配置と比較してください。"
        return StoneAnalysis(candidates, note)
    }

    private fun samplePatch(image: PixelImage, projection: BoardProjection, column: Double, row: Double): Patch {
        val center = projection.imagePointAt(column, row)!!
        val horizontal = projection.imagePointAt(if (column <= 17) column + 1.0 else column - 1.0, row)!!
        val vertical = projection.imagePointAt(column, if (row <= 17) row + 1.0 else row - 1.0)!!
        val hx = (horizontal.x - center.x) * (image.width - 1)
        val hy = (horizontal.y - center.y) * (image.height - 1)
        val vx = (vertical.x - center.x) * (image.width - 1)
        val vy = (vertical.y - center.y) * (image.height - 1)
        val shortSpacing = abs(hx * vy - hy * vx) / max(hypot(hx, hy), hypot(vx, vy))
        val indices = mutableSetOf<Int>()
        // 中心の罫線と星を避ける。射影後も盤面上で同じ範囲を調べる。
        val offsets = listOf(-0.32, -0.22, -0.12, 0.12, 0.22, 0.32)
        for (dy in offsets) for (dx in offsets) {
            if (hypot(dx, dy) > 0.4) continue
            val point = projection.imagePointAt(column + dx, row + dy) ?: continue
            val x = (point.x * (image.width - 1)).roundToInt()
            val y = (point.y * (image.height - 1)).roundToInt()
            if (x in 0 until image.width && y in 0 until image.height) indices.add(y * image.width + x)
        }
        val colors = indices.map { index -> features(image.pixel(index % image.width, index / image.width)) }
        return Patch(colors, shortSpacing >= 4.0 && colors.size >= 8)
    }

    private fun samplePatch(image: PixelImage, projection: BoardProjection, column: Int, row: Int) =
        samplePatch(image, projection, column.toDouble(), row.toDouble())

    private fun classifyPatch(column: Int, row: Int, colors: List<ColorSample>, wood: ColorSample): IntersectionCandidate {
        var dark = 0
        var pale = 0
        var similarWood = 0
        for (color in colors) {
            when {
                color.luminance < wood.luminance * 0.55 && color.saturation < max(0.4, wood.saturation * 0.9) -> dark++
                color.luminance > max(0.45, wood.luminance + 0.08) &&
                    color.saturation < max(0.15, wood.saturation * 0.55) &&
                    color.blueRatio > wood.blueRatio + 0.12 -> pale++
                abs(color.blueRatio - wood.blueRatio) < 0.16 &&
                    color.saturation >= max(0.15, wood.saturation * 0.6) &&
                    color.luminance in (wood.luminance * 0.55)..min(1.0, wood.luminance * 1.6) -> similarWood++
            }
        }
        val n = colors.size.toDouble()
        val state = when {
            dark / n >= 0.65 && pale / n <= 0.15 -> IntersectionState.BLACK
            pale / n >= 0.65 && dark / n <= 0.15 -> IntersectionState.WHITE
            similarWood / n >= 0.7 && dark / n <= 0.2 && pale / n <= 0.12 -> IntersectionState.EMPTY
            else -> IntersectionState.UNKNOWN
        }
        return IntersectionCandidate(column, row, state, if (state == IntersectionState.UNKNOWN) "色の混在や影・反射の可能性があります" else null)
    }

    private fun features(argb: Int): ColorSample {
        val red = (argb ushr 16 and 255) / 255.0
        val green = (argb ushr 8 and 255) / 255.0
        val blue = (argb and 255) / 255.0
        val brightest = max(red, max(green, blue))
        val darkest = min(red, min(green, blue))
        return ColorSample(
            red * 0.2126 + green * 0.7152 + blue * 0.0722,
            if (brightest == 0.0) 0.0 else (brightest - darkest) / brightest,
            if (red < 0.01) 0.0 else blue / red
        )
    }

    private fun median(values: List<Double>) = values.sorted()[values.size / 2]
}
