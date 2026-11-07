import AppKit
import CoreImage

// Separate setup window. The progress card remains a read-only surface.
final class WeChatLoginDelegate: NSObject, NSApplicationDelegate {
    let directory: URL
    var window: NSWindow!
    let status = NSTextField(wrappingLabelWithString: "正在准备微信连接…")
    let details = NSTextField(wrappingLabelWithString: "")
    let image = NSImageView()
    let code = NSTextField(string: "")
    let submit = NSButton(title: "提交配对码", target: nil, action: nil)
    var lastQR = ""
    var timer: Timer?

    init(directory: URL) { self.directory = directory }

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 420, height: 720),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "个人微信 · 连接小看板"
        window.isReleasedWhenClosed = false
        let title = NSTextField(labelWithString: "把任务发到微信")
        title.font = .systemFont(ofSize: 24, weight: .semibold)
        let subtitle = NSTextField(wrappingLabelWithString: "本人扫码连接 · 文字任务 · 进度和结果回传")
        subtitle.textColor = .secondaryLabelColor
        status.font = .systemFont(ofSize: 15)
        details.font = .systemFont(ofSize: 12)
        details.textColor = .secondaryLabelColor
        image.imageScaling = .scaleProportionallyUpOrDown
        code.placeholderString = "手机微信显示的数字"
        submit.target = self
        submit.action = #selector(submitCode)
        let pairing = NSStackView(views: [code, submit])
        pairing.orientation = .horizontal
        let stop = NSButton(title: "停止连接", target: self, action: #selector(stopService))
        let stack = NSStackView(views: [title, subtitle, image, status, pairing, details, stop])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 18
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 28),
            subtitle.widthAnchor.constraint(equalTo: stack.widthAnchor),
            status.widthAnchor.constraint(equalTo: stack.widthAnchor),
            details.widthAnchor.constraint(equalTo: stack.widthAnchor),
            image.widthAnchor.constraint(equalToConstant: 260),
            image.heightAnchor.constraint(equalToConstant: 260),
            code.widthAnchor.constraint(equalToConstant: 210)
        ])
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func refresh() {
        guard let data = try? Data(contentsOf: directory.appendingPathComponent("connection.json")),
              data.count < 262144,
              let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        status.stringValue = value["message"] as? String ?? "等待连接状态"
        let state = value["status"] as? String ?? ""
        let isRelay = value["mode"] as? String == "current_session"
        window.title = isRelay ? "个人微信 · 当前会话" : "个人微信 · 连接小看板"
        code.isHidden = state != "need_verifycode"
        submit.isHidden = code.isHidden
        let qr = value["qr"] as? String ?? ""
        if qr != lastQR {
            lastQR = qr
            image.image = nil
            if !qr.isEmpty, let filter = CIFilter(name: "CIQRCodeGenerator") {
                filter.setValue(Data(qr.utf8), forKey: "inputMessage")
                filter.setValue("M", forKey: "inputCorrectionLevel")
                if let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 8, y: 8)) {
                    let white = CIImage(color: .white).cropped(to: output.extent.insetBy(dx: -32, dy: -32))
                    let padded = output.composited(over: white)
                    if let cg = CIContext().createCGImage(padded, from: padded.extent) {
                        image.image = NSImage(cgImage: cg, size: NSSize(width: 260, height: 260))
                    }
                }
            }
        }
        if state == "connected" {
            image.image = NSImage(systemSymbolName: "checkmark.message.fill", accessibilityDescription: "已连接")
            let unsent = value["unsent"] as? Int ?? 0
            let tasks = value["tasks"] as? [String: Int] ?? [:]
            if isRelay {
                details.stringValue = "待发送回复 \(unsent) 条 · 消息记录 \(tasks.values.reduce(0, +)) 条\n"
                    + "连接同一段桌面对话，保留任务上下文。\n权限审批仍在原客户端处理。"
            } else {
                details.stringValue = "待发送回复 \(unsent) 条 · 任务记录 \(tasks.values.reduce(0, +)) 条\n"
                    + "当前只读工作区：\n" + (value["workspace"] as? String ?? "")
            }
        } else {
            details.stringValue = isRelay
                ? "连接凭据仅保存在本机。\n仅转发到已绑定的原会话。\n关闭此窗口不会停止服务。"
                : "连接凭据仅保存在本机。\n任务使用独立 Codex 会话，电脑需保持运行。\n关闭此窗口不会停止服务。"
        }
    }

    @objc func submitCode() {
        let value = code.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.range(of: "^[0-9]{4,12}$", options: .regularExpression) != nil,
              let data = try? JSONSerialization.data(withJSONObject: ["code": value]) else { return }
        let url = directory.appendingPathComponent("verify-code.json")
        do {
            try data.write(to: url, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
            code.stringValue = ""
            status.stringValue = "配对码已提交，正在确认…"
        } catch { status.stringValue = "无法写入配对码，请检查本机权限。" }
    }

    @objc func stopService() {
        do {
            try Data().write(to: directory.appendingPathComponent("stop-request"), options: .atomic)
            status.stringValue = "正在停止连接，最长约 35 秒…"
        } catch { status.stringValue = "无法停止服务，请检查本机权限。" }
    }
}

let application = NSApplication.shared
application.setActivationPolicy(.regular)
guard CommandLine.arguments.count == 2 else { exit(2) }
let delegate = WeChatLoginDelegate(directory: URL(fileURLWithPath: CommandLine.arguments[1]))
application.delegate = delegate
application.run()
