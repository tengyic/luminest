import Foundation
import CoreGraphics

// A Swift port of the core of perfect-freehand (steveruizgot/perfect-freehand), MIT.
// PencilKit is Catalyst-only, so macOS ink is this: a variable-width filled outline
// around the raw stroke. Only what the board uses is ported: size/thinning, pressure
// (real tablet pressure or a velocity-derived fallback), round start/end caps and
// taper. Easing and the last-point jitter guard are kept; streams and dot-capture
// are not needed here.

enum PerfectFreehand {

    struct Options {
        var size: CGFloat = 16
        var thinning: CGFloat = 0.5
        var smoothing: CGFloat = 0.5
        var easing: (CGFloat) -> CGFloat = { t in t * (2 - t) }  // easeOutQuad
        var simulatePressure: Bool = true
        var start: (taper: CGFloat, cap: Bool) = (0, true)
        var end: (taper: CGFloat, cap: Bool) = (0, true)
    }

    struct InputPoint {
        var point: CGPoint
        var pressure: CGFloat
    }

    struct StrokePoint {
        var point: CGPoint
        var pressure: CGFloat
        var distance: CGFloat
        var vector: CGVector
    }

    /// The filled outline for a stroke: an even count of points forming a closed loop
    /// (left side forward, cap, right side backward, cap).
    static func stroke(_ raw: [InputPoint], options: Options) -> [CGPoint] {
        let points = strokePoints(raw, options: options)
        return outline(points, options: options)
    }

    /// Convenience for the common call: uniform pressure (mouse ink).
    static func stroke(points: [CGPoint], size: CGFloat, thinning: CGFloat,
                       pressure: CGFloat) -> [CGPoint] {
        var options = Options()
        options.size = size
        options.thinning = thinning
        options.simulatePressure = false
        return stroke(points.map { InputPoint(point: $0, pressure: pressure) }, options: options)
    }

    // MARK: points

    static func strokePoints(_ raw: [InputPoint], options: Options) -> [StrokePoint] {
        guard !raw.isEmpty else { return [] }
        // Drop consecutive duplicates: a resting pen must not produce zero-length vectors.
        var inputs: [InputPoint] = []
        for item in raw where inputs.isEmpty || distance(item.point, inputs.last!.point) > 0.001 {
            inputs.append(item)
        }
        guard !inputs.isEmpty else { return [] }

        // Pressure: real when the hardware provides it (tablet), else derived from
        // speed — slow strokes are heavier, exactly the physical intuition.
        var pressures: [CGFloat] = []
        if !options.simulatePressure && inputs.count > 1 {
            pressures = inputs.map { min(1, max(0.05, $0.pressure)) }
        } else if inputs.count == 1 {
            pressures = [0.5]
        } else {
            for index in inputs.indices {
                let previous = inputs[max(0, index - 1)].point
                let current = inputs[index].point
                let next = inputs[min(inputs.count - 1, index + 1)].point
                let speed = distance(previous, next) / max(1, distance(previous, current) + distance(current, next))
                pressures.append(min(1, 1 - speed))
            }
            pressures[0] = 0.5
        }

        var result: [StrokePoint] = []
        var totalDistance: CGFloat = 0
        for (index, input) in inputs.enumerated() {
            if index == 0 {
                // The first vector points at the second; without it the cap is unstable.
                let vector = vectorBetween(input.point, inputs[min(1, inputs.count - 1)].point)
                result.append(StrokePoint(point: input.point, pressure: pressures[index],
                                          distance: 0, vector: vector))
                continue
            }
            totalDistance += distance(input.point, inputs[index - 1].point)
            let vector = vectorBetween(inputs[index - 1].point, input.point)
            result.append(StrokePoint(point: input.point, pressure: pressures[index],
                                      distance: totalDistance, vector: vector))
        }
        return result
    }

    // MARK: outline

    static func outline(_ points: [StrokePoint], options: Options) -> [CGPoint] {
        guard points.count > 0 else { return [] }
        if points.count == 1 {
            // A dot: a small circle around the single point.
            let radius = radius(at: points[0].pressure, options: options)
            return dot(at: points[0].point, radius: max(radius, 0.5))
        }

        let totalLength = points.last!.distance
        var left: [CGPoint] = []
        var right: [CGPoint] = []

        for (index, point) in points.enumerated() {
            var radius = radius(at: point.pressure, options: options)
            let taperStart = taperDistance(options.start.taper, total: totalLength)
            let taperEnd = taperDistance(options.end.taper, total: totalLength)

            if index == 0 && options.start.cap && taperStart == 0 { radius = 0 }
            if index == points.count - 1 && options.end.cap && taperEnd == 0 { radius = 0 }

            let startTaperOffset = taperStart > 0 ? min(1, point.distance / taperStart) : 1
            let endTaperOffset = taperEnd > 0 ? min(1, (totalLength - point.distance) / taperEnd) : 1
            let taperOffset = options.easing(min(startTaperOffset, endTaperOffset))
            radius *= taperOffset

            // The normal is perpendicular to the running direction; smoothing averages
            // neighbours so fast direction changes do not flare.
            let previous = points[max(0, index - 1)]
            let next = points[min(points.count - 1, index + 1)]
            let direction = index == 0 ? point.vector : normalized(CGVector(dx: next.point.x - previous.point.x,
                                                                            dy: next.point.y - previous.point.y))
            let normal = CGVector(dx: -direction.dy, dy: direction.dx)
            left.append(CGPoint(x: point.point.x + normal.dx * radius,
                                y: point.point.y + normal.dy * radius))
            right.append(CGPoint(x: point.point.x - normal.dx * radius,
                                 y: point.point.y - normal.dy * radius))
        }

        var outlinePoints: [CGPoint] = left
        // End cap, then the right side walked backwards, then the start cap.
        if options.end.cap, let last = points.last {
            outlinePoints.append(contentsOf: capArc(centre: last.point,
                                                    radius: radius(at: last.pressure, options: options),
                                                    direction: last.vector, forward: true))
        }
        outlinePoints.append(contentsOf: right.reversed())
        if options.start.cap, let first = points.first {
            outlinePoints.append(contentsOf: capArc(centre: first.point,
                                                    radius: radius(at: first.pressure, options: options),
                                                    direction: first.vector, forward: false))
        }
        return outlinePoints
    }

    private static func radius(at pressure: CGFloat, options: Options) -> CGFloat {
        let thinned = options.size / 2 * (1 - options.thinning * (1 - pressure))
        return max(0.3, thinned)
    }

    private static func taperDistance(_ requested: CGFloat, total: CGFloat) -> CGFloat {
        // A taper under 0 means "the whole stroke"; the library's convention.
        requested < 0 ? total : min(max(requested, 0), total)
    }

    private static func capArc(centre: CGPoint, radius: CGFloat,
                               direction: CGVector, forward: Bool) -> [CGPoint] {
        guard radius > 0.3 else { return [] }
        let angle = atan2(direction.dy, direction.dx)
        let start = forward ? angle - .pi / 2 : angle + .pi / 2
        let sweep: CGFloat = forward ? .pi : -.pi
        let steps = max(4, Int(abs(radius)))
        var arc: [CGPoint] = []
        for step in 1..<steps {
            let t = CGFloat(step) / CGFloat(steps)
            let theta = start + sweep * t
            arc.append(CGPoint(x: centre.x + cos(theta) * radius,
                               y: centre.y + sin(theta) * radius))
        }
        return arc
    }

    private static func dot(at centre: CGPoint, radius: CGFloat) -> [CGPoint] {
        var points: [CGPoint] = []
        for step in 0..<12 {
            let theta = CGFloat(step) / 12 * .pi * 2
            points.append(CGPoint(x: centre.x + cos(theta) * radius,
                                  y: centre.y + sin(theta) * radius))
        }
        return points
    }

    private static func distance(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        hypot(a.x - b.x, a.y - b.y)
    }

    private static func vectorBetween(_ from: CGPoint, _ to: CGPoint) -> CGVector {
        normalized(CGVector(dx: to.x - from.x, dy: to.y - from.y))
    }

    private static func normalized(_ vector: CGVector) -> CGVector {
        let length = hypot(vector.dx, vector.dy)
        guard length > 0.0001 else { return CGVector(dx: 1, dy: 0) }
        return CGVector(dx: vector.dx / length, dy: vector.dy / length)
    }
}

// Ramer–Douglas–Peucker, applied only at persistence time: the live stroke keeps every
// sample (display fidelity), the stored node keeps the shape at a fraction of the bytes.
enum RDP {
    static func simplify(_ points: [CGPoint], epsilon: CGFloat = 0.9) -> [CGPoint] {
        guard points.count > 2 else { return points }
        guard let (index, maximum) = furthest(points) else { return [points.first!, points.last!] }
        if maximum > epsilon {
            let head = simplify(Array(points[...index]), epsilon: epsilon)
            let tail = simplify(Array(points[index...]), epsilon: epsilon)
            return head.dropLast() + tail
        }
        return [points.first!, points.last!]
    }

    private static func furthest(_ points: [CGPoint]) -> (Int, CGFloat)? {
        guard let first = points.first, let last = points.last else { return nil }
        var bestIndex = 0
        var best: CGFloat = 0
        for (index, point) in points.enumerated() where index != 0 && index != points.count - 1 {
            let value = perpendicularDistance(point, first, last)
            if value > best { best = value; bestIndex = index }
        }
        return (bestIndex, best)
    }

    private static func perpendicularDistance(_ point: CGPoint, _ a: CGPoint, _ b: CGPoint) -> CGFloat {
        let dx = b.x - a.x, dy = b.y - a.y
        let length = hypot(dx, dy)
        guard length > 0.0001 else { return hypot(point.x - a.x, point.y - a.y) }
        return abs(dy * point.x - dx * point.y + b.x * a.y - b.y * a.x) / length
    }
}
