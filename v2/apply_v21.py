#!/usr/bin/env python3
"""PosterLab v2.1 overlay. Apply after v2/apply_v2.py."""
from pathlib import Path
import sys, shutil

if len(sys.argv) != 3:
    raise SystemExit("usage: apply_v21.py ENGINE OVERLAY")
root, overlay = Path(sys.argv[1]), Path(sys.argv[2])
ios = root / "ios-app"

def amend(path, old, new):
    p = ios / path
    s = p.read_text()
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, got {count}: {old[:90]!r}")
    p.write_text(s.replace(old, new, 1))

# Validate the original archive before invoking the Rust ZIP extractor.
amend("TendiesEngine.swift",
'''        let extractRC = destinationURL.path.withCString { arcC in''',
'''        try PosterLabIntegrity.validateArchive(destinationURL, log: { line in
            NSLog("PosterLab import validation: %@", line)
        })
        let extractRC = destinationURL.path.withCString { arcC in''')
amend("TendiesEngine.swift",
'''            let extractRC = item.fileURL.path.withCString { arcC in''',
'''            try PosterLabIntegrity.validateArchive(item.fileURL, log: log)
            let extractRC = item.fileURL.path.withCString { arcC in''')

# Replace legacy silent best-effort edits with strict, preserving, throwing edits.
amend("TendiesEngine.swift",
'''                updatePlistIdentifiers(
                    in: descItem.url,
                    randomizedID: randomizedID,
                    preserveSemanticIdentifiers: preservesSemanticIdentifiers
                )

                for sVer in versionsToWrite {''',
'''                try PosterLabDescriptor.prepare(
                    folder: descItem.url,
                    provider: descItem.ext,
                    id: randomizedID,
                    log: log
                )
                let stageSHA = try PosterLabIntegrity.stagingChecksum(descItem.url)
                log("本地待写目录指纹 SHA-256：\\(stageSHA)")
                log("此值只验证本地 staging，不代表设备端目标文件已回读。")

                for sVer in versionsToWrite {''')

# Original preferences are not backed up. Disable risky overwrite by default.
amend("AppViewModel.swift",
'''    @Published var resetPBProtections: Bool = true''',
'''    @Published var resetPBProtections: Bool = false''')
amend("TendiesView.swift",
'''                    Text("可选实验；不保证系统壁纸图库会重新注册")''',
'''                    Text("默认关闭。启用会改写 PosterBoard 偏好文件；没有设备端原始文件备份，可能覆盖已有配置。")
                        .foregroundStyle(.orange)''')

# Better partial-write messaging: previous descriptor writes are not rolled back on failure.
amend("AppViewModel.swift",
'''            tendiesFlashLog.append("❌ Error: \\(error.localizedDescription)")
            tendiesFlashPhase = .done(ok: false)''',
'''            tendiesFlashLog.append("❌ 写入中止：\\(error.localizedDescription)")
            tendiesFlashLog.append("重要：已经执行的设备端写入可能仍然存在；当前引擎没有自动回滚。")
            tendiesFlashPhase = .done(ok: false)''')

# Add the two local-only validation modules to the existing Xcode project.
for name in ["PosterLabIntegrity.swift", "PosterLabDescriptor.swift"]:
    shutil.copyfile(overlay / "v2" / name, ios / name)
p = root / "AirCard-iOS.xcodeproj/project.pbxproj"
s = p.read_text()
for i, name in enumerate(["PosterLabIntegrity.swift", "PosterLabDescriptor.swift"], start=3):
    file_id = f"AAED55D3000000000000010{i*2-2}"
    build_id = f"AAED55D3000000000000010{i*2-1}"
    # Distinct explicit 24-hex IDs for Xcode project references.
    if len(file_id) != 24 or len(build_id) != 24:
        raise SystemExit("Invalid PBX object ID")
    s = s.replace("/* End PBXBuildFile section */",
                  f"\t\t{build_id} /* {name} in Sources */ = {{isa = PBXBuildFile; fileRef = {file_id} /* {name} */; }};\n/* End PBXBuildFile section */", 1)
    s = s.replace("/* End PBXFileReference section */",
                  f'\t\t{file_id} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = {name}; sourceTree = "<group>"; }};\n/* End PBXFileReference section */',1)
    s = s.replace("/* PosterLabSafety.swift */,\n",
                  f"/* PosterLabSafety.swift */,\n\t\t\t\t{file_id} /* {name} */,\n",1)
    s = s.replace("/* PosterLabSafety.swift in Sources */,\n",
                  f"/* PosterLabSafety.swift in Sources */,\n\t\t\t\t{build_id} /* {name} in Sources */,\n",1)
p.write_text(s)
print("PosterLab v2.1 archive validation / strict rewrite / staged checks / safe defaults integrated")
