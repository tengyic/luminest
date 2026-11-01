import XCTest
@testable import LearningHarness

final class SimulationTests: XCTestCase {
    func testAllFifteenCurriculumExamples() throws {
        let examples: [(String, [String: Double], Double)] = [
            ("fraction", ["value":2], 0.75),
            ("number_line", ["value":5], 2),
            ("ratio", ["value":5], 20),
            ("expression", ["value":2], 16),
            ("balance", ["value":4], 19),
            ("number_line", ["value":-5], -8),
            ("slope", ["value":3], 2),
            ("linear", ["m":3,"b":-2,"value":4], 10),
            ("systems", ["m1":-1,"b1":7,"m2":1,"b2":-1,"value":4], 3),
            ("polynomial", ["value":2], 20),
            ("polynomial", ["value":-2], 0),
            ("quadratic", ["a":1,"b":-5,"c":6,"value":2], 0),
            ("probability", ["n":2,"p":0.5], 0.5),
            ("statistics", ["value":7], 4),
            ("sampling", ["value":20], sqrt(0.24/20))
        ]
        XCTAssertEqual(examples.count,15)
        for (kind, p, expected) in examples {
            let actual = try XCTUnwrap(SimulationMath.result(kind:kind,parameters:p,x:kind == "probability" ? 1 : nil),kind)
            XCTAssertEqual(actual,expected,accuracy:1e-10,kind)
            XCTAssertFalse(SimulationMath.equation(kind:kind,p:p).isEmpty)
        }
    }
    func testEveryKindRespondsToItsSlider() throws {
        for kind in SimulationMath.kinds.subtracting(["probability","slope"]) {
            let a = try XCTUnwrap(SimulationMath.result(kind:kind,parameters:["value":2]))
            let b = try XCTUnwrap(SimulationMath.result(kind:kind,parameters:["value":5]))
            XCTAssertNotEqual(a,b,kind)
        }
        XCTAssertNotEqual(SimulationMath.result(kind:"slope",parameters:["value":2]),SimulationMath.result(kind:"slope",parameters:["value":5]))
        XCTAssertNotEqual(SimulationMath.binomial(k:1,parameters:["n":2,"p":0.2]),SimulationMath.binomial(k:1,parameters:["n":2,"p":0.6]))
        XCTAssertNotEqual(SimulationMath.binomial(k:1,parameters:["n":2,"p":0.5]),SimulationMath.binomial(k:1,parameters:["n":4,"p":0.5]))
    }
    func testGraphCoefficientSlidersAndIdentities() throws {
        for (kind, ids) in [("linear",["m","b"]),("quadratic",["a","b","c"]),("systems",["m1","b1","m2","b2"])] {
            for id in ids {
                let secondary = id == "m2" || id == "b2"
                XCTAssertNotEqual(PlotMath.value(kind:kind,x:2,parameters:[id:2],secondary:secondary),PlotMath.value(kind:kind,x:2,parameters:[id:4],secondary:secondary),id)
            }
        }
        for x in [-5.0,-2,0,3,7] {
            for kind in ["expression","polynomial"] { XCTAssertEqual(PlotMath.value(kind:kind,x:x,parameters:[:]),PlotMath.value(kind:kind,x:x,parameters:[:],secondary:true)) }
        }
        XCTAssertEqual(PlotMath.value(kind:"balance",x:4,parameters:[:]),19)
        XCTAssertEqual(PlotMath.value(kind:"balance",x:-4,parameters:[:],secondary:true),19)
    }
    func testPositiveIntegerBoundsAndRounding() throws {
        for kind in ["fraction","sampling","probability"] {
            let schema = try JSON.make(["kind":kind,"parameters":[["id":"value","min":-10,"max":30,"value":-8]]])
            let p = try XCTUnwrap(SimulationMath.parameters(schema).first)
            XCTAssertEqual(p.range.lowerBound,1); XCTAssertEqual(p.value,1)
            XCTAssertEqual(SimulationMath.step(kind:kind,id:"value"),1)
        }
        XCTAssertEqual(SimulationMath.denominator(["value":2.6]),3)
        XCTAssertEqual(SimulationMath.denominator(["value":-10]),1)
        XCTAssertEqual(SimulationMath.sampleSize(["value":0]),1)
        XCTAssertEqual(SimulationMath.integer(.nan),1)
        XCTAssertEqual(SimulationMath.integer(.infinity),1)
        let ratio = try JSON.make(["kind":"ratio","parameters":[["id":"value","min":-10,"max":30,"value":-8]]])
        XCTAssertEqual(SimulationMath.parameters(ratio).first?.value,0)
        XCTAssertEqual(SimulationMath.result(kind:"ratio",parameters:["value":-10]),0)
    }
    func testUndefinedSlopeAndFiniteGuards() {
        XCTAssertNil(SimulationMath.result(kind:"slope",parameters:["value":0]))
        XCTAssertNil(PlotMath.value(kind:"slope",x:2,parameters:["value":0]))
        XCTAssertEqual(SimulationMath.result(kind:"slope",parameters:["value":-3]),-2)
        XCTAssertEqual(PlotMath.value(kind:"slope",x:4,parameters:["value":3]),8)
        XCTAssertTrue(SimulationMath.equation(kind:"slope",p:["value":0]).contains("undefined"))
        for kind in SimulationMath.kinds { XCTAssertNil(SimulationMath.result(kind:kind,parameters:["value":.nan])) }
        XCTAssertNil(SimulationMath.result(kind:"probability",parameters:["n":5],x:1.5))
        XCTAssertNil(PlotMath.value(kind:"fraction",x:2,parameters:[:]))
        XCTAssertNil(PlotMath.value(kind:"sampling",x:2,parameters:[:]))
        XCTAssertNil(PlotMath.value(kind:"arbitrary_code",x:2,parameters:[:]))
    }
    func testSystemsSpecialCases() throws {
        let point = try XCTUnwrap(SimulationMath.intersection([:]))
        XCTAssertEqual(point.x,4); XCTAssertEqual(point.y,3)
        XCTAssertNil(SimulationMath.intersection(["m1":2,"m2":2,"b1":1,"b2":3]))
        XCTAssertTrue(SimulationMath.equation(kind:"systems",p:["m1":2,"m2":2,"b1":1,"b2":3]).contains("no common solution"))
        XCTAssertTrue(SimulationMath.equation(kind:"systems",p:["m1":2,"m2":2,"b1":1,"b2":1]).contains("infinitely many"))
    }
    func testBinomialMassAndEndpoints() throws {
        for n in [1,2,10,40,100] {
            for p in [0.0,0.2,0.5,1.0] {
                let sum = (0...n).reduce(0.0) { $0 + (SimulationMath.binomial(k:$1,parameters:["n":Double(n),"p":p]) ?? 0) }
                XCTAssertEqual(sum,1,accuracy:1e-9)
            }
        }
        XCTAssertEqual(SimulationMath.binomial(k:2,parameters:["n":2,"p":1]),1)
        XCTAssertEqual(SimulationMath.binomial(k:-1,parameters:["n":2]),0)
    }
    func testStatisticsAndDeterministicSampling() {
        XCTAssertEqual(SimulationMath.median(SimulationMath.data(["value":7])),3.5)
        XCTAssertEqual(SimulationMath.median(SimulationMath.data(["value":-10])),2.5)
        XCTAssertEqual(SimulationMath.standardError(["value":80]),SimulationMath.standardError(["value":20])/2,accuracy:1e-12)
        XCTAssertEqual(SimulationMath.standardError(["value":20]),SimulationMath.standardError(["value":20]))
        XCTAssertTrue(SimulationMath.equation(kind:"sampling",p:["value":5]).contains("unreliable"))
        XCTAssertTrue(SimulationMath.equation(kind:"sampling",p:["value":100]).contains("not invented"))
    }
    func testSourceLinkSecurityAndComponentWhitelist() {
        XCTAssertNotNil(SafeLessonLink.url("https://example.com/lesson"))
        for url in ["http://example.com","file:///etc/passwd","javascript:alert(1)","https://user:password@example.com"] { XCTAssertNil(SafeLessonLink.url(url)) }
        XCTAssertFalse(LessonBlock.kinds.contains("script"))
        XCTAssertFalse(SimulationMath.kinds.contains("javascript"))
    }
}
