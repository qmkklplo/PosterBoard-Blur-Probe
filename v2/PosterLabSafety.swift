import Foundation
import CryptoKit

// PosterLab v2: package-local preflight and honest evidence collection.
// The current AirliftFFI API has write/inject methods, but NO device file-read
// primitive. Therefore this module does NOT claim remote checksum verification,
// device-side backup, or rollback. These need a new, verified transport API.
enum PosterLabSafety {
    enum SafetyError: LocalizedError {
        case invalidDescriptor(String)
        case unsafeItem(String)
        case oversizedFile(String)
        case tooManyFiles
        var errorDescription: String? {
            switch self {
            case .invalidDescriptor(let s): return "无效 Mercury 描述符：\(s)"
            case .unsafeItem(let s): return "壁纸包包含不安全路径或链接：\(s)"
            case .oversizedFile(let s): return "文件超过安全分析限制：\(s)"
            case .tooManyFiles: return "壁纸包内文件数量超出分析上限"
            }
        }
    }

    private static let maxFileBytes: Int64 = 128 * 1024 * 1024
    private static let maxFileCount = 20_000
    private static let maxDescriptorBytes: Int64 = 768 * 1024 * 1024

    static var reportDirectory: URL {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("PosterLabReports", isDirectory: true)
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }

    // Verify each local staging descriptor before any device write.
    // A SHA-256 written here verifies the local source, NOT the remote destination.
    static func preflight(
        descriptors: [(ext: String, url: URL)],
        wallpaperName: String,
        log: (String) -> Void
    ) throws {
        guard !descriptors.isEmpty else { throw SafetyError.invalidDescriptor("包中没有描述符") }
        guard descriptors.count <= 64 else { throw SafetyError.tooManyFiles }
        for descriptor in descriptors {
            let isMercury = descriptor.ext == "com.apple.MercuryPoster"
            if isMercury && UUID(uuidString: descriptor.url.lastPathComponent) == nil {
                throw SafetyError.invalidDescriptor("源目录不是 UUID，不能安全保留原生关联")
            }
            let root = descriptor.url.standardizedFileURL
            let prefix = root.path + "/"
            var count = 0
            var sum: Int64 = 0
            var preview: [String] = []
            guard let en = FileManager.default.enumerator(
                at: root,
                includingPropertiesForKeys: [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey, .fileSizeKey],
                options: []
            ) else { throw SafetyError.unsafeItem(root.lastPathComponent) }
            for case let item as URL in en {
                let path = item.standardizedFileURL.path
                guard path.hasPrefix(prefix) else { throw SafetyError.unsafeItem(path) }
                let vals = try item.resourceValues(forKeys: [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey, .fileSizeKey])
                if vals.isSymbolicLink == true { throw SafetyError.unsafeItem(item.lastPathComponent) }
                if vals.isDirectory == true { continue }
                guard vals.isRegularFile == true else { throw SafetyError.unsafeItem(item.lastPathComponent) }
                count += 1
                guard count <= maxFileCount else { throw SafetyError.tooManyFiles }
                let size = Int64(vals.fileSize ?? 0)
                guard size >= 0 && size <= maxFileBytes else { throw SafetyError.oversizedFile(item.lastPathComponent) }
                sum += size
                guard sum <= maxDescriptorBytes else { throw SafetyError.oversizedFile(root.lastPathComponent) }
                let data = try Data(contentsOf: item)
                let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
                // These checksums are an auditable LOCAL baseline only.
                if preview.count < 5 { preview.append("\(item.lastPathComponent): \(digest.prefix(16))") }
                if isMercury && item.lastPathComponent == "com.apple.posterkit.provider.contents.userInfo",
                   let info = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any] {
                    let look = info["lookIdentifier"].map { String(describing: $0) } ?? "未声明"
                    log("Celosia/Mercury userInfo.lookIdentifier: \(look)")
                }
            }
            log("预检查通过 · \(descriptor.ext) · \(count) 个文件 · \(sum) 字节")
            preview.forEach { log("本地 SHA-256: \($0)") }
            if isMercury { log("Mercury 原始 UUID / 语义标识符将保持不变") }
        }
    }

    static func exportReport(
        logLines: [String],
        galleryStatus: String,
        blurStatus: String,
        notes: String,
        wallpaperNames: [String]
    ) throws -> URL {
        // Do not store sensitive pairing secrets, raw VPN diagnostics or app files.
        let safeLines = logLines
            .filter { !$0.localizedCaseInsensitiveContains("pairing_file") &&
                      !$0.localizedCaseInsensitiveContains("host_alt_irk") }
            .map { $0.count > 4000 ? String($0.prefix(4000)) : $0 }
        let obj: [String: Any] = [
            "app": "PosterLab",
            "version": "2.0-alpha",
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "os": ProcessInfo.processInfo.operatingSystemVersionString,
            "wallpaperNames": wallpaperNames,
            "galleryVisible": galleryStatus,
            "celosiaHomeBlur": blurStatus,
            "notes": String(notes.prefix(5000)),
            "transport": "AirLift/AirTraffic",
            "transportAcknowledgement": "仅代表写入接口结果，不代表远端字节校验",
            "remoteReadbackVerified": false,
            "deviceBackupAvailable": false,
            "deviceRollbackAvailable": false,
            "systemGalleryVerifiedAutomatically": false,
            "log": safeLines
        ]
        let data = try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
        let stamp = Int(Date().timeIntervalSince1970)
        let url = reportDirectory.appendingPathComponent("PosterLab-\(stamp)-\(UUID().uuidString.prefix(8)).json")
        try data.write(to: url, options: .atomic)
        return url
    }

    static let verificationLimitations =
        "本版 AirliftFFI 仅提供写入/注入接口，缺少设备端读取 API，因此无法验证目标文件 SHA-256、备份原设备目录或自动回滚。若界面显示刷入完成，仅代表传输接口返回成功。"
}
