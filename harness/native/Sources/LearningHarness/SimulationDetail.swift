import SwiftUI

// This whitelist is data-only: lesson schemas never execute supplied code.
enum SimulationMath {
    static let kinds: Set<String> = ["fraction", "number_line", "ratio", "expression", "balance", "slope", "linear", "systems", "equations", "polynomial", "quadratic", "probability", "statistics", "sampling"]
    static func number(_ value: Double) -> String { value.formatted(.number.precision(.fractionLength(0...4))) }
    static func integer(_ value: Double, minimum: Double = 1, maximum: Double = 1000) -> Double {
        guard value.isFinite else { return minimum }
        return min(maximum, max(minimum, value.rounded()))
    }
    static func parameters(_ schema: JSON) -> [SimulationParameter] {
        let kind = schema["kind"].string.lowercased()
        return schema["parameters"].array.compactMap { json in
            guard var parameter = SimulationParameter.parse(json) else { return nil }
            let discrete = (kind == "fraction" && ["value", "denominator"].contains(parameter.id)) || (kind == "probability" && ["value", "n", "trials"].contains(parameter.id)) || (kind == "sampling" && ["value", "n"].contains(parameter.id))
            if discrete {
                let ceiling = kind == "probability" ? 100.0 : 1000.0
                let lo = min(ceiling - 1, max(1, parameter.range.lowerBound.rounded(.up)))
                let hi = max(lo + 1, min(ceiling, parameter.range.upperBound.rounded(.down)))
                parameter = SimulationParameter(id: parameter.id, label: parameter.label, range: lo...hi, value: integer(parameter.value, minimum: lo, maximum: hi))
            } else if kind == "ratio" && parameter.id == "value" {
                let lo = max(0, parameter.range.lowerBound), hi = max(lo + 1, parameter.range.upperBound)
                parameter = SimulationParameter(id: parameter.id, label: "Notebook count", range: lo...hi, value: min(hi, max(lo, parameter.value)))
            } else if kind == "probability" && ["p", "probability"].contains(parameter.id) {
                parameter = SimulationParameter(id: parameter.id, label: parameter.label, range: 0...1, value: min(1, max(0, parameter.value)))
            }
            return parameter
        }
    }
    static func step(kind: String, id: String) -> Double? {
        if kind == "fraction" || kind == "sampling" || (kind == "probability" && !["p", "probability"].contains(id)) { return 1 }
        return nil
    }
    static func input(_ p: [String: Double]) -> Double { p["value"] ?? 5 }
    static func denominator(_ p: [String: Double]) -> Double { integer(p["denominator"] ?? input(p)) }
    static func sampleSize(_ p: [String: Double]) -> Double { integer(p["n"] ?? input(p)) }
    static func data(_ p: [String: Double]) -> [Double] { [2, 3, 4, input(p)] }
    static func median(_ values: [Double]) -> Double { let a = values.sorted(); return (a[1] + a[2]) / 2 }
    static func standardError(_ p: [String: Double]) -> Double { sqrt(0.6 * 0.4 / sampleSize(p)) }
    static func binomial(k: Int, parameters p: [String: Double]) -> Double? {
        guard p.values.allSatisfy(\.isFinite) else { return nil }
        let n = Int(integer(p["n"] ?? p["trials"] ?? input(p), maximum: 100))
        let probability = min(1, max(0, p["p"] ?? p["probability"] ?? 0.5))
        guard k >= 0 && k <= n else { return 0 }
        if probability == 0 { return k == 0 ? 1 : 0 }
        if probability == 1 { return k == n ? 1 : 0 }
        var coefficient = 1.0
        if k > 0 { for i in 1...k { coefficient *= Double(n - k + i) / Double(i) } }
        let result = coefficient * pow(probability, Double(k)) * pow(1 - probability, Double(n - k))
        return result.isFinite ? result : nil
    }
    static func intersection(_ p: [String: Double]) -> (x: Double, y: Double)? {
        let m1 = p["m1"] ?? -1, m2 = p["m2"] ?? 1, b1 = p["b1"] ?? 7, b2 = p["b2"] ?? -1
        guard m1 != m2 else { return nil }
        let x = (b2 - b1) / (m1 - m2), y = m1 * x + b1
        return x.isFinite && y.isFinite ? (x, y) : nil
    }
    static func result(kind: String, parameters p: [String: Double], x: Double? = nil) -> Double? {
        guard p.values.allSatisfy(\.isFinite), x?.isFinite != false else { return nil }
        switch kind {
        case "fraction": return 1 / denominator(p) + 1 / (2 * denominator(p))
        case "number_line": return -3 + input(p)
        case "ratio": return 4 * max(0, input(p))
        case "statistics": return data(p).reduce(0, +) / 4
        case "sampling": return standardError(p)
        case "probability": guard let x, x == x.rounded(), abs(x) <= 1000 else { return nil }; return binomial(k: Int(x), parameters: p)
        case "slope": let dx = p["deltaX"] ?? input(p); return dx == 0 ? nil : 6 / dx
        default: return PlotMath.value(kind: kind, x: x ?? input(p), parameters: p)
        }
    }
    static func equation(kind: String, p: [String: Double]) -> String {
        let v = input(p), f = number
        switch kind {
        case "fraction": let d = denominator(p); return "1/\(f(d)) + 1/\(f(2*d)) = 2/\(f(2*d)) + 1/\(f(2*d)) = 3/\(f(2*d)) = \(f(3/(2*d)))"
        case "number_line": return "Start −3; signed movement \(f(v)): −3 + (\(f(v))) = \(f(-3+v))"
        case "ratio": return "12 ÷ 3 = 4 per notebook; 4 × \(f(max(0,v))) = \(f(4*max(0,v))) cost units"
        case "expression": return "3(x + 2) + 2x = 3x + 6 + 2x = 5x + 6; at x = \(f(v)): \(f(5*v+6))"
        case "balance": return "4x + 3 = 19; at x = \(f(v)): left = \(f(4*v+3)), right = 19; difference = \(f(4*v-16)). Solution x = 4."
        case "slope": let dx = p["deltaX"] ?? v; return "(1, 2) → (\(f(1+dx)), 8); Δy = 6, Δx = \(f(dx)); slope = " + (dx == 0 ? "undefined (vertical line)" : f(6/dx))
        case "linear": return "y = \(f(p["m"] ?? 3))x + (\(f(p["b"] ?? -2))); at x = \(f(v)): y = \(f(result(kind: kind, parameters: p) ?? 0))"
        case "systems", "equations":
            let lines = "y₁ = \(f(p["m1"] ?? -1))x + (\(f(p["b1"] ?? 7))); y₂ = \(f(p["m2"] ?? 1))x + (\(f(p["b2"] ?? -1)))"
            if let point = intersection(p) { return lines + "; intersection (\(f(point.x)), \(f(point.y))); at x = \(f(v)): y₁ = \(f(PlotMath.value(kind: kind, x: v, parameters: p) ?? 0)), y₂ = \(f(PlotMath.value(kind: kind, x: v, parameters: p, secondary: true) ?? 0))" }
            return lines + ((p["b1"] ?? 7) == (p["b2"] ?? -1) ? "; coincident: infinitely many solutions." : "; parallel: no common solution.")
        case "polynomial": return "(x + 2)(x + 3) = x² + 3x + 2x + 6 = x² + 5x + 6; x = \(f(v)): \(f((v+2)*(v+3)))"
        case "quadratic":
            let a = p["a"] ?? 1, b = p["b"] ?? -5, c = p["c"] ?? 6
            let description = a == 0 ? "a = 0: this is not a quadratic." : "Discriminant b² − 4ac = \(f(b*b-4*a*c)); vertex x = \(f(-b/(2*a)))."
            return "y = \(f(a))x² + (\(f(b)))x + (\(f(c))); x = \(f(v)): y = \(f(result(kind: kind, parameters: p) ?? 0)). " + description
        case "probability": let n = integer(p["n"] ?? p["trials"] ?? v, maximum: 100), probability = min(1,max(0,p["p"] ?? 0.5)); return "X ~ Binomial(n = \(f(n)), p = \(f(probability))). P(X = k) = C(n,k)pᵏ(1−p)ⁿ⁻ᵏ; E[X] = \(f(n*probability)). Independent trials, identical success probability; theoretical distribution, not observations."
        case "statistics": let a = data(p); return "Data: 2, 3, 4, \(f(v)); mean = \(f(a.reduce(0,+)/4)); median = \(f(median(a))); range = \(f(a.max()! - a.min()!)). The slider replaces the fourth value."
        case "sampling": let n = sampleSize(p), se = standardError(p); return "Assume population p = 0.60; n = \(f(n)). SE(p̂) = √(0.60 × 0.40/n) = \(f(se)); normal approximation: 0.60 ± 1.96 SE. " + (n*0.4 < 10 ? "Small sample: np and n(1−p) must both be ≥ 10; approximation is unreliable here." : "Assumes independent, representative sampling with negligible finite-population correction.") + " This is deterministic theoretical uncertainty, not invented sample data or an observed confidence interval."
        default: return "Invalid simulation kind."
        }
    }
}

struct SimulationDetail: View {
    let kind: String
    let parameters: [String: Double]
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if PlotMath.kinds.contains(kind), kind != "probability" {
                NativePlot(kind: kind, parameters: parameters).frame(height: 245)
            } else {
                semanticCanvas.frame(height: 210)
            }
            Text(SimulationMath.equation(kind: kind, p: parameters)).font(.system(size: 12, weight: .medium, design: .monospaced)).lineSpacing(5).textSelection(.enabled)
            Text(explanation).font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4)
        }.padding(14).background(Color.white.opacity(0.8), in: RoundedRectangle(cornerRadius: 15))
    }
    var explanation: String {
        switch kind {
        case "fraction": return "Each rectangle is the same whole. Use 2d equal parts: the first addend covers two, the second one. Only numerators add once units match."
        case "number_line": return "The filled dot is the result. Positive movement goes right and negative movement goes left from −3; the arrow shows direction."
        case "ratio": return "The unit price stays four. The count changes the cost bar and the corresponding point on the proportional line through zero."
        case "expression": return "The original and simplified expressions coincide for every x; the moving dot evaluates both, not just one selected example."
        case "balance": return "The two lines are the left and right quantities. Their intersection is equality. A point away from x = 4 does not balance the equation."
        case "slope": return "The dashed triangle shows rise six and the chosen horizontal run. Run zero produces a vertical segment, never an infinite numeric slope."
        case "polynomial": return "All four products x², 3x, 2x, and 6 are included. The graph is an algebraic identity for signed x; a physical rectangle requires x + 2 and x + 3 nonnegative."
        case "systems", "equations": return "Two independently controlled lines show both constraints. The moving dots test the same x in both; only their shared intersection solves the system."
        case "quadratic": return "Changing a controls curvature, b shifts the symmetry axis, c moves the intercept, and x moves the evaluated point. Real roots require a nonnegative discriminant."
        case "probability": return "Separate bars represent integer success counts k. Bar heights sum to one; changing n or p recomputes the entire probability mass function."
        case "statistics": return "Dots show each value; the solid vertical line is the mean and the dashed line is the median. Sorting is recomputed even when the replacement becomes the smallest value."
        case "sampling": return "The center stays at the assumed proportion; the uncertainty band narrows as n grows. Endpoints beyond [0,1] reveal the normal approximation's limitations; they are not silently clipped."
        default: return "Read the equation and trace the moving point as each parameter changes."
        }
    }
    var semanticCanvas: some View {
        Canvas { context, size in
            let w = max(1, size.width - 60), left = 30.0, y = size.height / 2
            func label(_ text: String, _ x: Double, _ yy: Double) { context.draw(Text(text).font(.system(size: 11)).foregroundColor(Palette.secondary), at: CGPoint(x: x, y: yy)) }
            func line(_ a: CGPoint, _ b: CGPoint, dashed: Bool = false) { var path = Path(); path.move(to: a); path.addLine(to: b); context.stroke(path, with: .color(Palette.forest), style: StrokeStyle(lineWidth: 2, dash: dashed ? [5,4] : [])) }
            func dot(_ x: Double, _ yy: Double, color: Color = Palette.forest) { context.fill(Path(ellipseIn: CGRect(x: x-5,y: yy-5,width: 10,height: 10)), with: .color(color)) }
            let v = SimulationMath.input(parameters), f = SimulationMath.number
            switch kind {
            case "fraction":
                let d = Int(SimulationMath.denominator(parameters)), cells = 2*d
                for row in 0..<3 {
                    let filled = [2,1,3][row], yy = 22.0 + Double(row)*55
                    for i in 0..<cells {
                        let rect = CGRect(x: left + Double(i)*w/Double(cells),y: yy,width: w/Double(cells),height: 30)
                        context.fill(Path(rect), with: .color(i < filled ? Palette.forest.opacity(0.75) : Palette.sage.opacity(0.25)))
                        if cells <= 160 { context.stroke(Path(rect), with: .color(.white), lineWidth: 1) }
                    }
                    label(["1/d = 2/(2d)","1/(2d)","sum = 3/(2d)"][row],size.width/2,yy+41)
                    // When d = 1, three half-units exceed one whole; show the extra half explicitly.
                    if filled > cells { context.fill(Path(CGRect(x: left,y: yy+31,width: w*Double(filled-cells)/Double(cells),height: 7)), with: .color(Palette.forest)); label("+ ½ whole",left+45,yy-10) }
                }
            case "number_line":
                let target = -3 + v, lo = min(-10,target-2), hi = max(10,target+2)
                func px(_ value: Double) -> Double { left + (value-lo)/(hi-lo)*w }
                line(CGPoint(x:left,y:y),CGPoint(x:left+w,y:y))
                for value in [-3.0,0,target] { dot(px(value),y); label(f(value),px(value),y+25) }
                line(CGPoint(x:px(-3),y:y-25),CGPoint(x:px(target),y:y-25))
                let direction = target >= -3 ? 1.0 : -1.0
                line(CGPoint(x:px(target)-direction*8,y:y-31),CGPoint(x:px(target),y:y-25)); line(CGPoint(x:px(target)-direction*8,y:y-19),CGPoint(x:px(target),y:y-25))
                label("signed change " + f(v),size.width/2,35)
            case "statistics":
                let data = SimulationMath.data(parameters), lo = min(0,data.min()!-2), hi = max(10,data.max()!+2)
                func px(_ value: Double) -> Double { left + (value-lo)/(hi-lo)*w }
                line(CGPoint(x:left,y:y),CGPoint(x:left+w,y:y))
                for (index,value) in data.enumerated() { dot(px(value),y-Double(index)*15); label(f(value),px(value),y+25+Double(index%2)*16) }
                let mean = data.reduce(0,+)/4, median = SimulationMath.median(data)
                line(CGPoint(x:px(mean),y:25),CGPoint(x:px(mean),y:y+5)); line(CGPoint(x:px(median),y:40),CGPoint(x:px(median),y:y+5),dashed:true)
                label("mean " + f(mean) + " · median " + f(median),size.width/2,185)
            case "sampling":
                let se = SimulationMath.standardError(parameters), lower = 0.6-1.96*se, upper = 0.6+1.96*se, lo = min(0,lower-0.05), hi = max(1,upper+0.05)
                func px(_ value: Double) -> Double { left+(value-lo)/(hi-lo)*w }
                line(CGPoint(x:left,y:y),CGPoint(x:left+w,y:y))
                context.fill(Path(CGRect(x:px(lower),y:y-22,width:px(upper)-px(lower),height:44)),with:.color(Palette.sage.opacity(0.7)))
                dot(px(0.6),y); label(f(lower),px(lower),y+40); label(f(upper),px(upper),y+40)
                label("assumed p = 0.60 · n = " + f(SimulationMath.sampleSize(parameters)),size.width/2,35)
                label("0",px(0),y-40); label("1",px(1),y-40)
            case "probability":
                let n = Int(SimulationMath.integer(parameters["n"] ?? parameters["trials"] ?? v,maximum:100))
                let masses = (0...n).map { SimulationMath.binomial(k:$0,parameters:parameters) ?? 0 }, peak = max(0.01,masses.max() ?? 1)
                for k in 0...n {
                    let height = masses[k]/peak*125, x = left+Double(k)*w/Double(n+1)
                    context.fill(Path(CGRect(x:x,y:160-height,width:max(1,w/Double(n+1)-2),height:height)),with:.color(Palette.forest.opacity(0.8)))
                    if n <= 12 || k == 0 || k == n { label(String(k),x+w/Double(n+1)/2,175) }
                }
                label("P(X=k) · tallest bar " + f(peak),size.width/2,15); label("integer success count k",size.width/2,198)
            default: break
            }
        }.accessibilityLabel(SimulationMath.equation(kind:kind,p:parameters))
    }
}
