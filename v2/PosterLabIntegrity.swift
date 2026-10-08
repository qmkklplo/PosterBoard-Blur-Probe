import Foundation
import CryptoKit

/// Validates the local ZIP archive and staged files, not the remote device.
enum PosterLabIntegrity {
    struct ValidationError: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }
    private static func fail(_ reason: String) -> ValidationError {
        ValidationError(message: "壁纸包检查失败：" + reason)
    }
    private static func value(_ data: Data, _ pos: Int, _ count: Int) throws -> UInt64 {
        guard pos >= 0, count > 0, pos <= data.count - count else { throw fail("压缩包字段越界") }
        var v: UInt64 = 0
        for i in 0..<count { v |= UInt64(data[pos+i]) << (i*8) }
        return v
    }

    /// Safe validation before calling the existing ZIP extraction library.
    static func validateArchive(_ url: URL, log: (String) -> Void) throws {
        let data = try Data(contentsOf: url, options: .mappedIfSafe)
        guard data.count >= 22, data.count <= 256*1024*1024 else {
            throw fail("压缩包大小不合理")
        }
        let first = max(0, data.count-65557)
        var footer: Int?
        for p in stride(from: data.count-22, through: first, by: -1) {
            if (try? value(data,p,4)) == 0x06054b50,
               let note = try? value(data,p+20,2),
               p+22+Int(note) == data.count {
                footer = p
                break
            }
        }
        guard let footer else { throw fail("没有找到 ZIP 目录") }
        let files = Int(try value(data,footer+10,2))
        let onDisk = Int(try value(data,footer+8,2))
        let size = try value(data,footer+12,4)
        let offset = try value(data,footer+16,4)
        guard files > 0, files <= 10000, onDisk == files,
              (try value(data,footer+4,2)) == 0,
              (try value(data,footer+6,2)) == 0,
              files != 65535, size != 0xffffffff, offset != 0xffffffff,
              offset+size <= UInt64(footer) else {
            throw fail("不支持 ZIP64、多卷压缩包或非法目录")
        }
        var cursor = Int(offset)
        let end = cursor+Int(size)
        var total: UInt64 = 0
        var unique = Set<String>()
        var realFiles = 0
        for _ in 0..<files {
            guard cursor+46 <= end, (try value(data,cursor,4)) == 0x02014b50 else {
                throw fail("目录项损坏")
            }
            let flags = try value(data,cursor+8,2)
            let method = try value(data,cursor+10,2)
            let size = try value(data,cursor+24,4)
            let nameSize = Int(try value(data,cursor+28,2))
            let extra = Int(try value(data,cursor+30,2))
            let comment = Int(try value(data,cursor+32,2))
            let external = try value(data,cursor+38,4)
            let length = 46+nameSize+extra+comment
            guard nameSize > 0, cursor+length <= end,
                  (flags & 1) == 0, method == 0 || method == 8,
                  size != 0xffffffff else { throw fail("不支持加密、损坏或非常规压缩条目") }
            let rawName = data.subdata(in: (cursor+46)..<(cursor+46+nameSize))
            guard let name = String(data:rawName, encoding:.utf8),
                  !name.hasPrefix("/"), !name.contains("\\"),
                  !name.contains(":"), !name.contains("\0"),
                  !name.split(separator:"/",omittingEmptySubsequences:false).dropLast().contains(".."),
                  !name.split(separator:"/",omittingEmptySubsequences:false).dropLast().contains(".") else {
                throw fail("发现不安全的文件名")
            }
            let parts = name.split(separator:"/",omittingEmptySubsequences:false)
            guard !parts.dropLast().contains(""), !parts.contains("..") else {
                throw fail("发现不安全的路径：\(name.prefix(80))")
            }
            let mode = (external >> 16) & 0xf000
            guard mode != 0xa000 else { throw fail("不允许符号链接") }
            guard unique.insert(name.precomposedStringWithCanonicalMapping.lowercased()).inserted else {
                throw fail("压缩包存在重复名称")
            }
            if !name.hasSuffix("/") {
                realFiles += 1
                guard size <= 128*1024*1024 else { throw fail("单个文件超过限制") }
                total += size
                guard total <= 768*1024*1024 else { throw fail("解压总量超过限制") }
            }
            cursor += length
        }
        guard cursor == end, realFiles > 0 else { throw fail("目录不完整") }
        let sha = SHA256.hash(data:data).map { String(format:"%02x",$0) }.joined()
        log("本地 ZIP 验证通过：\(realFiles) 个文件，预计展开 \(total) 字节")
        log("本地原始包 SHA-256：\(sha)")
    }

    /// Stable, deterministic checksum of the local staging directory.
    static func stagingChecksum(_ root: URL) throws -> String {
        let fm = FileManager.default
        guard let iterator = fm.enumerator(at:root,
            includingPropertiesForKeys:[.isRegularFileKey,.isSymbolicLinkKey],
            options:[]) else { throw fail("无法枚举壁纸描述符") }
        var list: [String] = []
        for case let file as URL in iterator {
            let props = try file.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey])
            guard props.isSymbolicLink != true else { throw fail("描述符包含符号链接") }
            guard props.isRegularFile == true else { continue }
            let bytes = try Data(contentsOf:file)
            let digest = SHA256.hash(data:bytes).map { String(format:"%02x",$0) }.joined()
            list.append(String(file.path.dropFirst(root.path.count+1)) + ":" + digest)
        }
        guard !list.isEmpty else { throw fail("没有可以写入的描述符文件") }
        return SHA256.hash(data:Data(list.sorted().joined(separator:"\n").utf8))
            .map { String(format:"%02x",$0) }.joined()
    }
}
