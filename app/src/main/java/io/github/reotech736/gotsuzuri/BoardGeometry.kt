package io.github.reotech736.gotsuzuri

import kotlin.math.abs
import kotlin.math.min

/** 向きを補正した画像内の正規化座標。碁盤の行・列とは別に保持する。 */
data class ImagePoint(val x: Double, val y: Double)

/** FIT_CENTER表示の画像領域。余白は画像座標に含めない。 */
data class ImageViewport(val left: Double, val top: Double, val width: Double, val height: Double) {
    fun toImage(x: Double, y: Double): ImagePoint? {
        if (!x.isFinite() || !y.isFinite() || x < left || x > left + width ||
            y < top || y > top + height
        ) return null
        return ImagePoint((x - left) / width, (y - top) / height)
    }

    fun toDisplay(point: ImagePoint) = ImagePoint(left + point.x * width, top + point.y * height)

    companion object {
        fun fit(imageWidth: Int, imageHeight: Int, viewWidth: Int, viewHeight: Int): ImageViewport? {
            if (imageWidth <= 0 || imageHeight <= 0 || viewWidth <= 0 || viewHeight <= 0) return null
            val scale = min(viewWidth.toDouble() / imageWidth, viewHeight.toDouble() / imageHeight)
            val width = imageWidth * scale
            val height = imageHeight * scale
            return ImageViewport((viewWidth - width) / 2, (viewHeight - height) / 2, width, height)
        }
    }
}

/** 論理碁盤の左上(0,0)〜右下(18,18)を画像へ射影する。石の分類は行わない。 */
class BoardProjection private constructor(private val coefficients: DoubleArray) {
    fun intersection(column: Int, row: Int): ImagePoint {
        require(column in 0..18 && row in 0..18)
        return imagePointAt(column.toDouble(), row.toDouble())!!
    }

    /** 交点周辺の色を盤面上の一定間隔で調べるための連続座標。盤外は推測しない。 */
    fun imagePointAt(column: Double, row: Double): ImagePoint? {
        if (!column.isFinite() || !row.isFinite() || column !in 0.0..18.0 || row !in 0.0..18.0) {
            return null
        }
        val u = column / 18.0
        val v = row / 18.0
        val denominator = coefficients[6] * u + coefficients[7] * v + 1
        return ImagePoint(
            (coefficients[0] * u + coefficients[1] * v + coefficients[2]) / denominator,
            (coefficients[3] * u + coefficients[4] * v + coefficients[5]) / denominator
        )
    }

    companion object {
        private const val EPSILON = 1e-8

        /** 左上→右上→右下→左下。重複・交差・凹形・退化した四角形は表示しない。 */
        fun fromCorners(corners: List<ImagePoint>): BoardProjection? {
            if (corners.size != 4 || corners.any {
                    !it.x.isFinite() || !it.y.isFinite() || it.x !in 0.0..1.0 || it.y !in 0.0..1.0
                }
            ) return null
            for (index in 0..3) {
                val a = corners[index]
                val b = corners[(index + 1) % 4]
                val c = corners[(index + 2) % 4]
                val cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x)
                if (cross <= EPSILON) return null
            }
            val (p0, p1, p2, p3) = corners
            val dx1 = p1.x - p2.x
            val dx2 = p3.x - p2.x
            val dx3 = p0.x - p1.x + p2.x - p3.x
            val dy1 = p1.y - p2.y
            val dy2 = p3.y - p2.y
            val dy3 = p0.y - p1.y + p2.y - p3.y
            val g: Double
            val h: Double
            if (abs(dx3) < EPSILON && abs(dy3) < EPSILON) {
                g = 0.0
                h = 0.0
            } else {
                val determinant = dx1 * dy2 - dx2 * dy1
                if (abs(determinant) < EPSILON) return null
                g = (dx3 * dy2 - dx2 * dy3) / determinant
                h = (dx1 * dy3 - dx3 * dy1) / determinant
            }
            if (listOf(1.0, 1 + g, 1 + h, 1 + g + h).any { !it.isFinite() || it <= EPSILON }) {
                return null
            }
            return BoardProjection(doubleArrayOf(
                p1.x - p0.x + g * p1.x, p3.x - p0.x + h * p3.x, p0.x,
                p1.y - p0.y + g * p1.y, p3.y - p0.y + h * p3.y, p0.y, g, h
            ))
        }
    }
}
