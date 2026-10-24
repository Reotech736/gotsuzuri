package io.github.reotech736.gotsuzuri

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNotNull
import org.junit.Test
import kotlin.math.hypot

class StoneClassifierTest {
    private val size = 721
    private val boardColor = 0xFFB98B50.toInt()
    private val corners = listOf(ImagePoint(0.05, 0.05), ImagePoint(0.95, 0.05), ImagePoint(0.95, 0.95), ImagePoint(0.05, 0.95))
    private val projection = BoardProjection.fromCorners(corners)!!

    private fun board() = IntArray(size * size) { boardColor }.also { pixels ->
        for (row in 0..18) for (column in 0..18) {
            val point = projection.intersection(column, row)
            val x = (point.x * (size - 1)).toInt()
            val y = (point.y * (size - 1)).toInt()
            for (delta in -1..1) {
                for (i in 36..684) {
                    pixels[(y + delta) * size + i] = 0xFF302818.toInt()
                    pixels[i * size + x + delta] = 0xFF302818.toInt()
                }
            }
        }
    }

    private fun disk(pixels: IntArray, column: Int, row: Int, color: Int, dx: Double = 0.0, dy: Double = 0.0) {
        val point = projection.imagePointAt(column + dx, row + dy)!!
        val cx = (point.x * (size - 1)).toInt()
        val cy = (point.y * (size - 1)).toInt()
        for (dy in -15..15) for (dx in -15..15) {
            if (hypot(dx.toDouble(), dy.toDouble()) <= 15) pixels[(cy + dy) * size + cx + dx] = color
        }
    }

    private fun state(result: StoneAnalysis, column: Int, row: Int) = result.candidates[row * 19 + column].state

    @Test fun emptyGridLinesAreNotBlackStones() {
        val result = StoneClassifier.analyze(PixelImage(size, size, board()), projection)
        assertEquals(361, result.count(IntersectionState.EMPTY))
        assertEquals(0, result.count(IntersectionState.BLACK))
    }

    @Test fun findsIsolatedBlackAndWhiteWithoutChangingOtherIntersections() {
        val pixels = board()
        disk(pixels, 3, 4, 0xFF202020.toInt())
        disk(pixels, 13, 15, 0xFFE8E8E0.toInt())
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.BLACK, state(result, 3, 4))
        assertEquals(IntersectionState.WHITE, state(result, 13, 15))
        assertEquals(359, result.count(IntersectionState.EMPTY))
    }

    @Test fun adjacentStonesAreKeptAtSeparateLogicalCoordinates() {
        val pixels = board()
        disk(pixels, 8, 9, 0xFF151515.toInt())
        disk(pixels, 9, 9, 0xFFF0F0F0.toInt())
        disk(pixels, 10, 9, 0xFF151515.toInt())
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.BLACK, state(result, 8, 9))
        assertEquals(IntersectionState.WHITE, state(result, 9, 9))
        assertEquals(IntersectionState.BLACK, state(result, 10, 9))
    }

    @Test fun edgesAndCornersAreSampledWithoutReadingOutsideImage() {
        val pixels = board()
        disk(pixels, 0, 0, 0xFF202020.toInt())
        disk(pixels, 18, 9, 0xFFE8E8E0.toInt())
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.BLACK, state(result, 0, 0))
        assertEquals(IntersectionState.WHITE, state(result, 18, 9))
    }

    @Test fun mixedBlackAndWhiteRegionIsUnknown() {
        val pixels = board()
        disk(pixels, 9, 9, 0xFF151515.toInt())
        for (y in 345..375) for (x in 360..375) {
            if (hypot((x - 360).toDouble(), (y - 360).toDouble()) <= 15) pixels[y * size + x] = 0xFFF0F0F0.toInt()
        }
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.UNKNOWN, state(result, 9, 9))
    }

    @Test fun missingWoodReferenceDoesNotProduceConfidentEmptyBoard() {
        for (color in listOf(0xFF000000.toInt(), 0xFFFFFFFF.toInt(), 0xFF808080.toInt())) {
            val result = StoneClassifier.analyze(PixelImage(size, size, IntArray(size * size) { color }), projection)
            assertEquals(361, result.count(IntersectionState.UNKNOWN))
            assertTrue(result.note.contains("推定できない"))
        }
    }

    @Test fun tooFewPixelsAreUnknown() {
        val result = StoneClassifier.analyze(PixelImage(37, 37, IntArray(37 * 37) { boardColor }), projection)
        assertEquals(361, result.count(IntersectionState.UNKNOWN))
    }

    @Test fun findsShiftedStoneTopsWithoutMovingTheLogicalIntersections() {
        val pixels = board()
        disk(pixels, 5, 7, 0xFF151515.toInt(), dx = 0.2, dy = -0.35)
        disk(pixels, 13, 12, 0xFFF0F0F0.toInt(), dx = -0.2, dy = 0.35)
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.BLACK, state(result, 5, 7))
        assertEquals(IntersectionState.WHITE, state(result, 13, 12))
        assertEquals(1, result.count(IntersectionState.BLACK))
        assertEquals(1, result.count(IntersectionState.WHITE))
        val detected = result.candidates[7 * 19 + 5].stoneCenter
        assertNotNull(detected)
        assertTrue(detected!!.y < projection.intersection(5, 7).y)
        assertTrue(state(result, 5, 6) !in listOf(IntersectionState.BLACK, IntersectionState.WHITE))
    }

    @Test fun shiftedAdjacentDifferentColorsAreNotSwappedOrDuplicated() {
        val pixels = board()
        disk(pixels, 8, 9, 0xFF151515.toInt(), dy = -0.3)
        disk(pixels, 9, 9, 0xFFF0F0F0.toInt(), dy = -0.3)
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.BLACK, state(result, 8, 9))
        assertEquals(IntersectionState.WHITE, state(result, 9, 9))
        assertEquals(1, result.count(IntersectionState.BLACK))
        assertEquals(1, result.count(IntersectionState.WHITE))
    }

    @Test fun shiftedEdgeStoneDoesNotReadOutsideBoardOrImage() {
        val pixels = board()
        disk(pixels, 0, 8, 0xFF151515.toInt(), dy = -0.3)
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.BLACK, state(result, 0, 8))
        assertEquals(1, result.count(IntersectionState.BLACK))
        assertEquals(361, result.candidates.size)
    }

    @Test fun stoneHalfwayBetweenTwoIntersectionsIsUnknownRatherThanDuplicated() {
        val pixels = board()
        disk(pixels, 9, 8, 0xFF151515.toInt(), dy = 0.5)
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(IntersectionState.UNKNOWN, state(result, 9, 8))
        assertEquals(IntersectionState.UNKNOWN, state(result, 9, 9))
        assertEquals(0, result.count(IntersectionState.BLACK))
    }

    @Test fun doesNotPlaceAWhiteCandidateOnWoodColoredPixelsInsideItsPatch() {
        val pixels = board()
        disk(pixels, 9, 9, 0xFFF0F0F0.toInt())
        for (y in 358..362) for (x in 358..362) pixels[y * size + x] = boardColor
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(1, result.count(IntersectionState.WHITE))
        val candidate = result.candidates[9 * 19 + 9].stoneCenter!!
        val x = (candidate.x * (size - 1)).toInt()
        val y = (candidate.y * (size - 1)).toInt()
        assertEquals(0xFFF0F0F0.toInt(), pixels[y * size + x])
    }

    @Test fun smallHighlightMovesTheBlackCandidateInsteadOfLosingTheStone() {
        val pixels = board()
        disk(pixels, 9, 9, 0xFF151515.toInt())
        for (y in 358..362) for (x in 358..362) pixels[y * size + x] = 0xFFF0F0F0.toInt()
        val result = StoneClassifier.analyze(PixelImage(size, size, pixels), projection)
        assertEquals(1, result.count(IntersectionState.BLACK))
        assertEquals(0, result.count(IntersectionState.WHITE))
        val candidate = result.candidates[9 * 19 + 9].stoneCenter!!
        val x = (candidate.x * (size - 1)).toInt()
        val y = (candidate.y * (size - 1)).toInt()
        assertEquals(0xFF151515.toInt(), pixels[y * size + x])
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsInvalidPixelBuffer() {
        PixelImage(20, 20, IntArray(10))
    }
}
