import SwiftUI

// MARK: - Viewport

/// Where the camera is: the board coordinate fixed at the centre of the view, and the
/// scale. One struct so a fit or a zoom-at-cursor is one allocation of the rules rather
/// than four copies of them.
struct BoardViewport {
    var centre = CGPoint(x: 3000, y: 2000)
    var zoom: CGFloat = 0.55

    static let minimumZoom: CGFloat = 0.12
    static let maximumZoom: CGFloat = 7

    /// Board point → view point. The view is centred, not origin-anchored, so panning is
    /// changing `centre` rather than tracking a translation offset.
    func toView(_ point: CGPoint, in size: CGSize) -> CGPoint {
        CGPoint(x: (point.x - centre.x) * zoom + size.width / 2,
                y: (point.y - centre.y) * zoom + size.height / 2)
    }

    func toBoard(_ point: CGPoint, in size: CGSize) -> CGPoint {
        CGPoint(x: (point.x - size.width / 2) / zoom + centre.x,
                y: (point.y - size.height / 2) / zoom + centre.y)
    }

    /// Zoom by a factor while keeping the board point under `location` exactly still.
    ///
    /// Zooming about the view centre is the default in most apps and is why a zoomed-in
    /// canvas always drifts away from whatever you were looking at. Anchoring to the
    /// pointer means the cursor keeps pointing at the same ink.
    mutating func zoom(by factor: CGFloat, at location: CGPoint, in size: CGSize) {
        let anchor = toBoard(location, in: size)
        let target = (zoom * factor).clamped(to: Self.minimumZoom...Self.maximumZoom)
        guard target != zoom else { return }
        zoom = target
        let moved = toBoard(location, in: size)
        centre.x += anchor.x - moved.x
        centre.y += anchor.y - moved.y
    }

    /// Frame the whole board with breathing room. Padding is in board units so the same
    /// margin applies at every zoom level.
    mutating func fit(_ bounds: CGRect, in size: CGSize, padding: CGFloat = 120) {
        guard bounds.width > 0.5, bounds.height > 0.5, size.width > 10, size.height > 10 else { return }
        let inset = bounds.insetBy(dx: -padding, dy: -padding)
        let target = min(size.width / inset.width, size.height / inset.height)
        zoom = target.clamped(to: Self.minimumZoom...Self.maximumZoom)
        centre = CGPoint(x: inset.midX, y: inset.midY)
    }
}

extension Comparable {
    fileprivate func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}
