// macOS Vision OCR —— 批量识别图片文字，输出 JSON
//
// 编译：swiftc -O -framework Vision -framework AppKit subtitle_ocr.swift -o subtitle_ocr
// 用法：./subtitle_ocr frames/*.jpg > ocr.json
//
// 输出： [{ "file": "f_001.jpg", "lines": [ { "text": "...", "conf": 0.9, "x": .., "y": .., "h": .. } ] }]
//   x / y / h 为归一化坐标，Vision 原点在【左下】—— y 越大越靠上。
//   字幕通常在 y 0.15~0.45（画面中下部）；角落的水印/UI 用坐标剔除。

import Foundation
import Vision
import AppKit

var results: [[String: Any]] = []

for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let cg = rep.cgImage else {
        results.append(["file": path, "error": "load_failed"])
        continue
    }

    var lines: [[String: Any]] = []
    let request = VNRecognizeTextRequest { req, _ in
        guard let obs = req.results as? [VNRecognizedTextObservation] else { return }
        for o in obs {
            guard let top = o.topCandidates(1).first else { continue }
            lines.append([
                "text": top.string,
                "conf": Double(round(top.confidence * 100) / 100),
                "x": Double(round(o.boundingBox.origin.x * 1000) / 1000),
                "y": Double(round(o.boundingBox.origin.y * 1000) / 1000),
                "h": Double(round(o.boundingBox.height * 1000) / 1000),
            ])
        }
    }
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true

    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try handler.perform([request])
    } catch {
        results.append(["file": path, "error": "ocr_failed"])
        continue
    }
    // 自上而下排序
    lines.sort { ($0["y"] as! Double) > ($1["y"] as! Double) }
    results.append([
        "file": (path as NSString).lastPathComponent,
        "lines": lines,
    ])
}

let data = try! JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted, .withoutEscapingSlashes])
FileHandle.standardOutput.write(data)
