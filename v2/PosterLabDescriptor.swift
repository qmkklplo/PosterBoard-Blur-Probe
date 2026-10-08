import Foundation

/// Metadata-preserving descriptor preparation. Runs entirely on local staging.
enum PosterLabDescriptor {
    static func prepare(folder: URL, provider: String, id: Int, log: (String) -> Void) throws {
        let fm = FileManager.default
        let hasSuggestionMetadata = fm.fileExists(
            atPath: folder.appendingPathComponent("com.apple.posterkit.provider.identifierURL.suggestionMetadata.plist").path)
        if provider == "com.apple.MercuryPoster" || hasSuggestionMetadata {
            log("保留原生 provider 标识符：\(provider)（无强制改写）")
            return
        }
        guard let iterator = fm.enumerator(at:folder,
               includingPropertiesForKeys:[.isRegularFileKey,.isSymbolicLinkKey],options:[]) else {
            throw NSError(domain:"PosterLab",code:202,
                userInfo:[NSLocalizedDescriptionKey:"无法读取壁纸描述符"])
        }
        var changed = 0
        for case let file as URL in iterator {
            let props = try file.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey])
            guard props.isSymbolicLink != true else {
                throw NSError(domain:"PosterLab",code:203,
                    userInfo:[NSLocalizedDescriptionKey:"描述符包含符号链接"])
            }
            guard props.isRegularFile == true else { continue }
            let name = file.lastPathComponent
            if name == "com.apple.posterkit.provider.descriptor.identifier" {
                let contents = try Data(contentsOf:file)
                if let value = String(data:contents,encoding:.utf8)?
                    .trimmingCharacters(in:.whitespacesAndNewlines),
                   Int(value) != nil {
                    try Data(String(id).utf8).write(to:file,options:.atomic)
                    changed += 1
                }
            } else if name == "com.apple.posterkit.provider.contents.userInfo" ||
                        name == "Wallpaper.plist" {
                let original = try Data(contentsOf:file)
                var format = PropertyListSerialization.PropertyListFormat.binary
                guard var dict = try PropertyListSerialization.propertyList(
                    from:original,options:[],format:&format) as? [String:Any] else {
                    throw NSError(domain:"PosterLab",code:204,
                       userInfo:[NSLocalizedDescriptionKey:"无法解析 \(name)，已停止刷入"])
                }
                let key = name == "Wallpaper.plist" ? "identifier" : "wallpaperRepresentingIdentifier"
                if dict[key] == nil { continue }
                dict[key] = id
                let output = try PropertyListSerialization.data(
                    fromPropertyList:dict,format:format,options:0)
                try output.write(to:file,options:.atomic)
                changed += 1
            }
        }
        log("普通壁纸标识符修改完成：\(changed) 处，已保留不适合随机化的符号 ID")
    }
}
