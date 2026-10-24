package io.github.reotech736.gotsuzuri

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BoardGeometryTest {
    private val square = listOf(
        ImagePoint(0.0, 0.0), ImagePoint(1.0, 0.0), ImagePoint(1.0, 1.0), ImagePoint(0.0, 1.0)
    )

    private fun assertPoint(expected: ImagePoint, actual: ImagePoint) {
        assertEquals(expected.x, actual.x, 1e-9)
        assertEquals(expected.y, actual.y, 1e-9)
    }

    @Test fun squareHasNineteenRowsAndColumnsIncludingBoundary() {
        val projection = BoardProjection.fromCorners(square)!!
        val grid = (0..18).flatMap { row -> (0..18).map { column -> projection.intersection(column, row) } }
        assertEquals(361, grid.distinct().size)
        assertPoint(square[0], projection.intersection(0, 0))
        assertPoint(square[1], projection.intersection(18, 0))
        assertPoint(square[2], projection.intersection(18, 18))
        assertPoint(square[3], projection.intersection(0, 18))
        assertPoint(ImagePoint(0.5, 0.5), projection.intersection(9, 9))
        assertPoint(ImagePoint(1 / 18.0, 17 / 18.0), projection.intersection(1, 17))
    }

    @Test fun tiltedParallelogramUsesAffineMapping() {
        val corners = listOf(ImagePoint(0.2, 0.1), ImagePoint(0.8, 0.2), ImagePoint(0.9, 0.9), ImagePoint(0.3, 0.8))
        assertPoint(ImagePoint(0.55, 0.5), BoardProjection.fromCorners(corners)!!.intersection(9, 9))
    }

    @Test fun perspectiveMatchesIndependentKnownTransformAtAllIntersections() {
        fun expected(u: Double, v: Double): ImagePoint {
            val denominator = 0.4 * u + 0.2 * v + 1
            return ImagePoint((0.8 * u + 0.1 * v + 0.05) / denominator, (0.05 * u + 0.6 * v + 0.1) / denominator)
        }
        val corners = listOf(expected(0.0, 0.0), expected(1.0, 0.0), expected(1.0, 1.0), expected(0.0, 1.0))
        val projection = BoardProjection.fromCorners(corners)!!
        for (row in 0..18) for (column in 0..18) {
            assertPoint(expected(column / 18.0, row / 18.0), projection.intersection(column, row))
        }
    }

    @Test fun stronglyForeshortenedBoardHasFinitePoints() {
        val corners = listOf(ImagePoint(0.45, 0.1), ImagePoint(0.55, 0.1), ImagePoint(0.95, 0.9), ImagePoint(0.05, 0.9))
        val projection = BoardProjection.fromCorners(corners)!!
        for (row in 0..18) for (column in 0..18) {
            val point = projection.intersection(column, row)
            assertTrue(point.x.isFinite() && point.y.isFinite())
            assertTrue(point.x in 0.0..1.0 && point.y in 0.0..1.0)
        }
    }

    @Test fun rejectsMissingAndExtraCorners() {
        assertNull(BoardProjection.fromCorners(emptyList()))
        assertNull(BoardProjection.fromCorners(square.take(3)))
        assertNull(BoardProjection.fromCorners(square + square.first()))
    }

    @Test fun rejectsDuplicateCollinearAndTinyQuadrilaterals() {
        assertNull(BoardProjection.fromCorners(listOf(square[0], square[0], square[2], square[3])))
        assertNull(BoardProjection.fromCorners(listOf(ImagePoint(0.0, 0.0), ImagePoint(0.3, 0.3), ImagePoint(0.6, 0.6), ImagePoint(0.9, 0.9))))
        assertNull(BoardProjection.fromCorners(square.map { ImagePoint(it.x * 1e-6, it.y * 1e-6) }))
    }

    @Test fun rejectsCrossedConcaveAndCounterclockwiseCorners() {
        assertNull(BoardProjection.fromCorners(listOf(square[0], square[2], square[1], square[3])))
        assertNull(BoardProjection.fromCorners(listOf(square[0], square[1], ImagePoint(0.2, 0.2), square[3])))
        assertNull(BoardProjection.fromCorners(square.reversed()))
    }

    @Test fun rejectsNonfiniteAndOutOfImagePoints() {
        for (bad in listOf(ImagePoint(Double.NaN, 0.0), ImagePoint(0.0, Double.POSITIVE_INFINITY), ImagePoint(-0.01, 0.0), ImagePoint(0.0, 1.01))) {
            assertNull(BoardProjection.fromCorners(listOf(bad) + square.drop(1)))
        }
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsLogicalCoordinatesOutsideBoard() {
        BoardProjection.fromCorners(square)!!.intersection(19, 0)
    }

    @Test fun portraitLetterboxExcludesTopAndBottomPadding() {
        val frame = ImageViewport.fit(300, 400, 600, 1000)!!
        assertEquals(100.0, frame.top, 1e-9)
        assertNull(frame.toImage(300.0, 99.0))
        assertNull(frame.toImage(300.0, 901.0))
        assertPoint(ImagePoint(0.0, 0.0), frame.toImage(0.0, 100.0)!!)
        assertPoint(ImagePoint(1.0, 1.0), frame.toImage(600.0, 900.0)!!)
    }

    @Test fun landscapeLetterboxExcludesSidePaddingAndRoundTrips() {
        val frame = ImageViewport.fit(300, 400, 1000, 600)!!
        assertEquals(275.0, frame.left, 1e-9)
        assertNull(frame.toImage(274.0, 300.0))
        assertNull(frame.toImage(726.0, 300.0))
        assertNull(frame.toImage(Double.NaN, 300.0))
        val point = ImagePoint(0.37, 0.62)
        val shown = frame.toDisplay(point)
        assertPoint(point, frame.toImage(shown.x, shown.y)!!)
    }

    @Test fun resizedViewKeepsImageCoordinates() {
        val point = ImagePoint(0.2, 0.7)
        for ((width, height) in listOf(600 to 1000, 1000 to 600, 500 to 500)) {
            val frame = ImageViewport.fit(3072, 4096, width, height)!!
            val shown = frame.toDisplay(point)
            assertPoint(point, frame.toImage(shown.x, shown.y)!!)
        }
    }

    @Test fun zeroSizesHaveNoViewport() {
        assertNull(ImageViewport.fit(0, 400, 600, 1000))
        assertNull(ImageViewport.fit(300, 0, 600, 1000))
        assertNull(ImageViewport.fit(300, 400, 0, 1000))
        assertNull(ImageViewport.fit(300, 400, 600, 0))
        assertNotNull(ImageViewport.fit(1, 1, 1, 1))
    }
}
