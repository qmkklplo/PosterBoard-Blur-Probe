#!/usr/bin/env python3
"""PosterLab v2 overlay: uses authorized MIT AirCard/AirliftFFI source.
Deliberately does not claim remote readback or device rollback.
"""
from pathlib import Path
import sys, shutil, json

if len(sys.argv) != 3:
    raise SystemExit("usage: apply_v2.py /path/to/engine /path/to/overlay")
base, overlay = Path(sys.argv[1]), Path(sys.argv[2])
ios = base / "ios-app"

def read(relative):
    return (ios / relative).read_text(encoding="utf-8")
def save(relative, content):
    (ios / relative).write_text(content, encoding="utf-8")
def once(s, anchor, replacement, label):
    if s.count(anchor) != 1:
        raise SystemExit(f"Expected one {label}; found {s.count(anchor)}")
    return s.replace(anchor, replacement, 1)

# Keep existing RPPairing / LocalDevVPN / AirliftFFI device transport,
# while reducing the root UI to device connection and wallpapers.
s = read("ContentView.swift")
head = s.index("struct ContentView: View {")
start = s.index("        TabView(selection: $vm.selectedTab) {", head)
end = s.index('        .alert("Notice"', start)
s = s[:start] + '''        TabView(selection: $vm.selectedTab) {
            PairingTab()
                .tabItem { Label("设备连接", systemImage: "antenna.radiowaves.left.and.right") }
                .tag(AppTab.pairing)

            TendiesView()
                .tabItem { Label("壁纸实验室", systemImage: "photo.stack.fill") }
                .tag(AppTab.wallpapers)
        }
''' + s[end:]
s = s.replace('Text("AirCard-iOS")', 'Text("PosterLab v2")', 1)
save("ContentView.swift", s)

s = read("TendiesEngine.swift")
s = once(s, "import Foundation\n", "import Foundation\nimport CryptoKit\n", "Engine Foundation import")
# For safety, prohibit multi-package transactions until true device backup and
# rollback are available. AirLift's current FFI provides no remote read/delete.
s = once(
    s,
    '''        guard !items.isEmpty else {
            log("⚠️ No wallpapers selected to flash")
            return
        }
''',
    '''        guard !items.isEmpty else {
            throw NSError(domain: "PosterLab", code: 100,
                userInfo: [NSLocalizedDescriptionKey: "没有选择壁纸包"])
        }
        guard items.count == 1 else {
            throw NSError(domain: "PosterLab", code: 101,
                userInfo: [NSLocalizedDescriptionKey: "v2 安全模式每次只能刷入一个壁纸包；请逐个刷入并记录结果。"])
        }
''',
    "single package safety gate"
)
s = once(
    s,
    '''            guard extractRC == 0 else {
                log("❌ Failed to extract '\(item.name)'")
                continue
            }
''',
    '''            guard extractRC == 0 else {
                log("壁纸包解压失败，已经取消安装；不会虚报刷入成功。")
                throw NSError(domain: "PosterLab", code: 102,
                    userInfo: [NSLocalizedDescriptionKey: "壁纸包解压失败，请检查 .tendies 文件完整性。"])
            }
''',
    "archive extract failure"
)

# Enforce safe package staging before any write; hashes are LOCAL baseline only.
marker = '            log("  ✨ Found \\(descriptors.count) descriptor(s) to install")'
if marker not in s: raise SystemExit("Missing descriptor enumeration")
s = once(s, marker, marker + '''
            try PosterLabSafety.preflight(
                descriptors: descriptors,
                wallpaperName: item.name,
                log: log
            )
            log("注意：AirLift 接口无远端 read API，不能证明目标目录字节相同。")
''', "preflight insertion")

# Legacy source preserves Mercury UUID and semantic identifiers.
for needle in ['preservesMercuryDescriptorUUID', 'preserveSemanticIdentifiers: preservesSemanticIdentifiers']:
    if needle not in s: raise SystemExit(f"Missing Mercury protection: {needle}")

# Make PosterBoard preference writes genuinely optional instead of only changing UI.
start = s.index("        // Always force PosterBoard cache refresh and file protections reset", s.index("public func flashTendies("))
end = s.index("        progress(1.0)", start)
s = s[:start] + '''        if resetProtections {
            log("PosterBoard 刷新偏好已启用（实验性，不代表系统图库已注册）")
''' + s[start:end] + '''        } else {
            log("根据用户选择，跳过 PosterBoard 刷新偏好写入。")
        }

''' + s[end:]
s = s.replace('log("\\n🎉 All wallpapers injected successfully! Open Lock Screen settings or long-press lockscreen to choose your new wallpaper.")',
'''log("设备端注入 API 返回成功；尚未完成远端回读、图库注册、Celosia 动态模糊验证。")''')
save("TendiesEngine.swift", s)

s = read("AppViewModel.swift")
start = s.index('            tendiesFlashLog.append("🎉 Wallpapers applied successfully!")', s.index("func flashSelectedTendies() async"))
end = s.index("        } catch {", start)
s = s[:start] + '''            tendiesFlashLog.append("设备写入接口返回成功。系统壁纸图库和动态模糊状态需要单独确认。")
            tendiesFlashLog.append("v2 默认不自动 NeoSpring，请在日志确认后按需手动执行。")
''' + s[end:]
save("AppViewModel.swift", s)

s = read("TendiesView.swift")
s = once(s, '    @State private var isNeoSpringing = false',
'''    @State private var isNeoSpringing = false
    @State private var galleryCheck = "未验证"
    @State private var blurCheck = "未验证"
    @State private var sessionNotes = ""
    @State private var reportURL: URL?
    @State private var sharingReport = false''', "TendiesView states")
s = once(s, '''            Form {
''', '''            Form {
                Section {
                    Label("PosterLab v2 · 壁纸实验室", systemImage: "square.stack.3d.up")
                        .font(.headline)
                    Text("本地预检查 + SHA-256 基线 + Mercury 原生标识保护 + AirLift 注入")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text(PosterLabSafety.verificationLimitations)
                        .font(.caption)
                        .foregroundStyle(.orange)
                }

''', "TendiesView header")
s = s.replace('Choose .tendies from Files…','导入 .tendies 壁纸包')
s = s.replace('Import More Wallpapers…','继续导入壁纸')
s = s.replace('Force PosterBoard Cache Refresh','尝试刷新 PosterBoard 偏好')
s = s.replace('Resets file protections so iOS re-indexes wallpapers immediately','可选实验；不保证系统壁纸图库会重新注册')
s = s.replace('Flashing Wallpapers…','正在检查并刷入壁纸…')
s = s.replace('Flashing will automatically trigger NeoSpring to respring the device and apply your new wallpapers.',
              '完成写入后不会自动 NeoSpring；请先导出日志。')
s = s.replace('.navigationTitle("Wallpapers")','.navigationTitle("PosterLab v2")')
log_marker = '''                // Section 5: Flash Log (CompactLogView)'''
new_section = '''                // v2: manual system checks are part of the evidence chain.
                Section {
                    Picker("系统图库", selection: $galleryCheck) {
                        Text("未验证").tag("未验证")
                        Text("可见").tag("可见")
                        Text("不可见").tag("不可见")
                    }
                    Picker("Celosia 主屏幕模糊", selection: $blurCheck) {
                        Text("未验证").tag("未验证")
                        Text("随时间变化").tag("随时间变化")
                        Text("停留旧画面").tag("停留旧画面")
                    }
                    TextField("测试备注（可选）", text: $sessionNotes, axis: .vertical)
                        .lineLimit(2...4)
                    Button {
                        do {
                            reportURL = try PosterLabSafety.exportReport(
                                logLines: vm.tendiesFlashLog,
                                galleryStatus: galleryCheck,
                                blurStatus: blurCheck,
                                notes: sessionNotes,
                                wallpaperNames: vm.tendieItems
                                    .filter { $0.isSelected }
                                    .map { $0.name }
                            )
                            sharingReport = true
                        } catch {
                            vm.errorMessage = "导出报告失败：" + error.localizedDescription
                        }
                    } label: {
                        Label("导出本次诊断报告（JSON）", systemImage: "square.and.arrow.up")
                    }
                    Text("图库与模糊结果由你手动确认；报告不会把接口成功误写为远端回读成功。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Celosia · 结果确认")
                }

'''
s = once(s, log_marker, new_section + log_marker, "diagnostic section")
sheet_anchor = '''            .sheet(isPresented: $showFilePicker) {'''
s = once(s, sheet_anchor, '''            .sheet(isPresented: $sharingReport) {
                if let reportURL = reportURL {
                    ShareSheet(items: [reportURL])
                }
            }
''' + sheet_anchor, "report share sheet")
save("TendiesView.swift", s)

s = read("Info.plist")
s = s.replace("<string>AirCard-iOS</string>", "<string>PosterLab</string>", 1)
s = s.replace("AirCard-iOS advertises", "PosterLab advertises")
save("Info.plist", s)

shutil.copyfile(overlay / "v2/PosterLabSafety.swift", ios / "PosterLabSafety.swift")
project = base / "AirCard-iOS.xcodeproj/project.pbxproj"
p = project.read_text()
build_id = "AAED55D30000000000000101"
file_id = "AAED55D30000000000000102"
p = once(p, "/* End PBXBuildFile section */",
f'\t\t{build_id} /* PosterLabSafety.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {file_id} /* PosterLabSafety.swift */; }};\n/* End PBXBuildFile section */', "PBXBuildFile")
p = once(p, "/* End PBXFileReference section */",
f'\t\t{file_id} /* PosterLabSafety.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = PosterLabSafety.swift; sourceTree = "<group>"; }};\n/* End PBXFileReference section */', "PBXFileReference")
p = once(p, '\t\t\t\tA416E9FC1E5258B289C6DA54 /* TendiesView.swift */,\n',
f'\t\t\t\tA416E9FC1E5258B289C6DA54 /* TendiesView.swift */,\n\t\t\t\t{file_id} /* PosterLabSafety.swift */,\n', "PBXGroup")
p = once(p, '\t\t\t\t80E5245336B574F61E0D3194 /* TendiesView.swift in Sources */,\n',
f'\t\t\t\t80E5245336B574F61E0D3194 /* TendiesView.swift in Sources */,\n\t\t\t\t{build_id} /* PosterLabSafety.swift in Sources */,\n', "PBXSourcesBuildPhase")
project.write_text(p)

# Copy the approved new icon. Re-upscale on macOS for all required asset slots.
icon_b64 = overlay / "v2/app-icon.jpg.b64"
if not icon_b64.is_file(): raise SystemExit("Missing approved icon source")
import base64
icon_dir = ios / "Assets.xcassets/AppIcon.appiconset"
src_icon = icon_dir / "posterlab-source.jpg"
src_icon.write_bytes(base64.b64decode(icon_b64.read_text().strip()))
icon_dims = [('AppIcon.png',1024),('AppIcon-60@2x.png',120),
             ('AppIcon-60@3x.png',180),('AppIcon-76@2x.png',152),
             ('AppIcon-83.5@2x.png',167)]
import subprocess
for filename,dimension in icon_dims:
    subprocess.run(['sips','-s','format','png','-z',str(dimension),str(dimension),
                    str(src_icon),'--out',str(icon_dir / filename)],
                    check=True,stdout=subprocess.DEVNULL)
src_icon.unlink()

# Sanity checks: no false guarantee, selected icon and safety code actually in target.
assert 'PosterLabSafety.preflight(' in read('TendiesEngine.swift')
assert 'if resetProtections {' in read('TendiesEngine.swift')
assert 'reportURL = try PosterLabSafety.exportReport' in read('TendiesView.swift')
assert 'DispatchQueue.main.asyncAfter' not in read('AppViewModel.swift')[read('AppViewModel.swift').index('func flashSelectedTendies() async'):read('AppViewModel.swift').index('func respringDevice()')]
assert (icon_dir / 'AppIcon.png').stat().st_size > 10000
print('PosterLab v2 overlay applied: graphics, safety checks, manual evidence reports')
