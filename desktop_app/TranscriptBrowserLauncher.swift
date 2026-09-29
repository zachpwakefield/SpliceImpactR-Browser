import AppKit
import CryptoKit
import Darwin
import Foundation

private enum LauncherRuntimeError: LocalizedError {
    case missingEmbeddedRuntime
    case invalidRuntimeManifest(URL)
    case missingVerifiedDatabase
    case runtimeIntegrity(String)
    case missingPython

    var errorDescription: String? {
        switch self {
        case .missingEmbeddedRuntime:
            return "The application does not contain its local runtime package. Rebuild and install it from your checkout."
        case .invalidRuntimeManifest(let url):
            return "The runtime manifest is missing or invalid at \(url.path)."
        case .missingVerifiedDatabase:
            return "The private verified data clone is missing. Re-run desktop_app/install_macos_app.sh once."
        case .runtimeIntegrity(let path):
            return "A private runtime file is missing or changed (\(path)). Reinstall the launcher after stopping it."
        case .missingPython:
            return "The Python installation used to build this app is unavailable. Restore Python and re-run desktop_app/install_macos_app.sh."
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var port = 8765
    private var expectedBuildHash = ""
    private var expectedFrontendHash = ""
    private var pythonURL: URL?
    private var expectedPythonVersion = ""
    private let selfTest = CommandLine.arguments.contains("--self-test")
    var exitCode: Int32 = 0
    private var window: NSWindow!
    private var statusLabel: NSTextField!
    private var detailLabel: NSTextField!
    private var openButton: NSButton!
    private var retryButton: NSButton!
    private var quitButton: NSButton!
    private var progress: NSProgressIndicator!
    private var serverProcess: Process?
    private var serverLogHandle: FileHandle?
    private var runtimeURL: URL?
    private var ownsServer = false
    private var serverIsReady = false
    private var didOpenBrowser = false
    private var isTerminating = false
    private var launchGeneration = 0
    private var readinessStarted = Date()

    private var serverURL: URL {
        URL(string: "http://127.0.0.1:\(port)")!
    }

    private var manifestURL: URL {
        serverURL.appendingPathComponent("api/v1/manifest")
    }

    private var logURL: URL {
        if let root = testStateRoot {
            return root.appendingPathComponent("Logs/server.log")
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Transcript Browser/server.log")
    }

    // Explicit isolation for the documented native self-test; normal launches
    // always use this user's Application Support and Logs directories.
    private var testStateRoot: URL? {
        guard selfTest, let index = CommandLine.arguments.firstIndex(of: "--state-root"),
              index + 1 < CommandLine.arguments.count else { return nil }
        return URL(fileURLWithPath: CommandLine.arguments[index + 1], isDirectory: true)
            .standardizedFileURL.resolvingSymlinksInPath()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(selfTest ? .prohibited : .regular)
        configureMenu()
        configureWindow()
        if !selfTest { NSApp.activate(ignoringOtherApps: true) }
        beginLaunch()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationShouldHandleReopen(
        _ sender: NSApplication,
        hasVisibleWindows flag: Bool
    ) -> Bool {
        if !flag {
            window.makeKeyAndOrderFront(nil)
        }
        NSApp.activate(ignoringOtherApps: true)
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        isTerminating = true
        launchGeneration += 1
        if ownsServer, let process = serverProcess, process.isRunning {
            process.terminate()
            if selfTest { process.waitUntilExit() }
        }
        try? serverLogHandle?.close()
    }

    private func configureMenu() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)

        let appMenu = NSMenu()
        let openItem = NSMenuItem(
            title: "Open Transcript Browser",
            action: #selector(openBrowser(_:)),
            keyEquivalent: "o"
        )
        openItem.target = self
        appMenu.addItem(openItem)
        appMenu.addItem(.separator())
        let quitItem = NSMenuItem(
            title: "Stop & Quit Transcript Browser",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )
        appMenu.addItem(quitItem)
        appMenuItem.submenu = appMenu
        NSApp.mainMenu = mainMenu
    }

    private func configureWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 310),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Transcript Browser"
        window.isReleasedWhenClosed = false
        window.center()

        let content = NSView()
        content.translatesAutoresizingMaskIntoConstraints = false
        window.contentView = content

        let symbol = NSImageView()
        symbol.translatesAutoresizingMaskIntoConstraints = false
        symbol.image = NSImage(
            systemSymbolName: "point.3.filled.connected.trianglepath.dotted",
            accessibilityDescription: "Transcript Browser"
        ) ?? NSImage(named: NSImage.applicationIconName)
        symbol.contentTintColor = NSColor(calibratedRed: 0.10, green: 0.36, blue: 0.31, alpha: 1)
        symbol.imageScaling = .scaleProportionallyUpOrDown

        let title = NSTextField(labelWithString: "Transcript Browser")
        title.translatesAutoresizingMaskIntoConstraints = false
        title.font = .systemFont(ofSize: 24, weight: .semibold)
        title.textColor = NSColor(calibratedRed: 0.08, green: 0.24, blue: 0.21, alpha: 1)

        let subtitle = NSTextField(labelWithString: "GENCODE v45 · verified local workspace")
        subtitle.translatesAutoresizingMaskIntoConstraints = false
        subtitle.font = .systemFont(ofSize: 12, weight: .medium)
        subtitle.textColor = .secondaryLabelColor

        progress = NSProgressIndicator()
        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.style = .spinning
        progress.controlSize = .small
        progress.startAnimation(nil)

        statusLabel = NSTextField(labelWithString: "Starting the local server…")
        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.font = .systemFont(ofSize: 14, weight: .semibold)
        statusLabel.textColor = .labelColor
        statusLabel.lineBreakMode = .byWordWrapping
        statusLabel.maximumNumberOfLines = 2

        detailLabel = NSTextField(wrappingLabelWithString: "No Terminal window will open. The service is available only on this Mac at 127.0.0.1.")
        detailLabel.translatesAutoresizingMaskIntoConstraints = false
        detailLabel.font = .systemFont(ofSize: 11)
        detailLabel.textColor = .secondaryLabelColor
        detailLabel.maximumNumberOfLines = 4

        openButton = NSButton(title: "Open Browser", target: self, action: #selector(openBrowser(_:)))
        openButton.translatesAutoresizingMaskIntoConstraints = false
        openButton.bezelStyle = .rounded
        openButton.keyEquivalent = "\r"
        openButton.isEnabled = false

        retryButton = NSButton(title: "Retry", target: self, action: #selector(retryLaunch(_:)))
        retryButton.translatesAutoresizingMaskIntoConstraints = false
        retryButton.bezelStyle = .rounded
        retryButton.isHidden = true

        quitButton = NSButton(title: "Stop & Quit", target: NSApp, action: #selector(NSApplication.terminate(_:)))
        quitButton.translatesAutoresizingMaskIntoConstraints = false
        quitButton.bezelStyle = .rounded

        [symbol, title, subtitle, progress, statusLabel, detailLabel, openButton, retryButton, quitButton]
            .forEach(content.addSubview)

        NSLayoutConstraint.activate([
            symbol.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 30),
            symbol.topAnchor.constraint(equalTo: content.topAnchor, constant: 28),
            symbol.widthAnchor.constraint(equalToConstant: 50),
            symbol.heightAnchor.constraint(equalToConstant: 50),

            title.leadingAnchor.constraint(equalTo: symbol.trailingAnchor, constant: 16),
            title.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -28),
            title.topAnchor.constraint(equalTo: content.topAnchor, constant: 27),

            subtitle.leadingAnchor.constraint(equalTo: title.leadingAnchor),
            subtitle.trailingAnchor.constraint(equalTo: title.trailingAnchor),
            subtitle.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 3),

            progress.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 31),
            progress.topAnchor.constraint(equalTo: symbol.bottomAnchor, constant: 37),
            progress.widthAnchor.constraint(equalToConstant: 18),
            progress.heightAnchor.constraint(equalToConstant: 18),

            statusLabel.leadingAnchor.constraint(equalTo: progress.trailingAnchor, constant: 12),
            statusLabel.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -30),
            statusLabel.centerYAnchor.constraint(equalTo: progress.centerYAnchor),

            detailLabel.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 31),
            detailLabel.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -31),
            detailLabel.topAnchor.constraint(equalTo: statusLabel.bottomAnchor, constant: 13),

            quitButton.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 30),
            quitButton.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -27),

            retryButton.trailingAnchor.constraint(equalTo: openButton.leadingAnchor, constant: -9),
            retryButton.centerYAnchor.constraint(equalTo: openButton.centerYAnchor),

            openButton.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -30),
            openButton.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -27),
        ])

        if !selfTest { window.makeKeyAndOrderFront(nil) }
    }

    private func safeRuntimeFile(_ root: URL, relative: String) throws -> URL {
        if try root.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink == true {
            throw LauncherRuntimeError.runtimeIntegrity("runtime directory")
        }
        let parts = relative.split(separator: "/", omittingEmptySubsequences: false)
        guard !parts.isEmpty, !relative.hasPrefix("/"),
              !parts.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }) else {
            throw LauncherRuntimeError.runtimeIntegrity(relative)
        }
        var path = root
        for part in parts {
            path.appendPathComponent(String(part))
            let values = try path.resourceValues(forKeys: [.isSymbolicLinkKey])
            if values.isSymbolicLink == true { throw LauncherRuntimeError.runtimeIntegrity(relative) }
        }
        return path
    }

    private func sha256(_ path: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: path)
        defer { try? handle.close() }
        var digest = SHA256()
        while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty {
            digest.update(data: data)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private func prepareRuntime() throws -> (URL, [String: Any]) {
        guard let resources = Bundle.main.resourceURL else {
            throw LauncherRuntimeError.missingEmbeddedRuntime
        }
        let archive = resources.appendingPathComponent("Runtime.zip")
        let embeddedManifest = resources.appendingPathComponent("Runtime-manifest.json")
        guard FileManager.default.fileExists(atPath: archive.path) else {
            throw LauncherRuntimeError.missingEmbeddedRuntime
        }
        let embeddedData = try Data(contentsOf: embeddedManifest)
        guard let metadata = try JSONSerialization.jsonObject(with: embeddedData) as? [String: Any],
              metadata["schema"] as? String == "transcript-browser-macos-runtime/v1",
              let version = metadata["runtimeVersion"] as? String,
              version.count == 64, version.allSatisfy({ "0123456789abcdef".contains($0) }),
              let buildHash = metadata["buildHash"] as? String, !buildHash.isEmpty,
              let frontendHash = metadata["frontendIndexSha256"] as? String,
              frontendHash.count == 64,
              let interpreter = metadata["pythonExecutable"] as? String, interpreter.hasPrefix("/"),
              let pythonVersion = metadata["pythonVersion"] as? String, !pythonVersion.isEmpty,
              let bundledFiles = metadata["bundledFiles"] as? [String: Any],
              let externalFiles = metadata["externalFiles"] as? [String: Any] else {
            throw LauncherRuntimeError.invalidRuntimeManifest(embeddedManifest)
        }
        guard FileManager.default.isExecutableFile(atPath: interpreter) else {
            throw LauncherRuntimeError.missingPython
        }
        let fileManager = FileManager.default
        let stateRoot: URL
        if let root = testStateRoot {
            stateRoot = root
        } else {
            stateRoot = try fileManager.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
                .appendingPathComponent("Transcript Browser", isDirectory: true)
        }
        let cached = stateRoot.appendingPathComponent("Runtime", isDirectory: true)
            .appendingPathComponent(version, isDirectory: true)
        guard fileManager.fileExists(atPath: cached.path),
              try Data(contentsOf: safeRuntimeFile(cached, relative: "runtime-manifest.json")) == embeddedData else {
            throw LauncherRuntimeError.missingVerifiedDatabase
        }
        for (relative, rawRecord) in bundledFiles {
            guard let record = rawRecord as? [String: Any],
                  let expectedSize = record["size"] as? NSNumber,
                  let expectedHash = record["sha256"] as? String else {
                throw LauncherRuntimeError.invalidRuntimeManifest(embeddedManifest)
            }
            let file = try safeRuntimeFile(cached, relative: relative)
            guard try file.resourceValues(forKeys: [.fileSizeKey]).fileSize == expectedSize.intValue,
                  try sha256(file) == expectedHash else {
                throw LauncherRuntimeError.runtimeIntegrity(relative)
            }
        }
        for (relative, rawRecord) in externalFiles {
            guard let record = rawRecord as? [String: Any], let size = record["size"] as? NSNumber else {
                throw LauncherRuntimeError.invalidRuntimeManifest(embeddedManifest)
            }
            let file = try safeRuntimeFile(cached, relative: relative)
            guard try file.resourceValues(forKeys: [.fileSizeKey]).fileSize == size.intValue else {
                throw LauncherRuntimeError.missingVerifiedDatabase
            }
        }
        return (cached, metadata)
    }

    private func beginLaunch(allowReuse: Bool = true) {
        launchGeneration += 1
        let generation = launchGeneration
        serverIsReady = false
        didOpenBrowser = false
        openButton.isEnabled = false
        retryButton.isHidden = true
        progress.isHidden = false
        progress.startAnimation(nil)
        statusLabel.stringValue = "Preparing the verified local service…"
        detailLabel.stringValue = "Checking the private runtime prepared by the installer. No Terminal window will open."
        runtimeURL = nil
        pythonURL = nil
        port = 8765

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            var preparedRuntime: (URL, [String: Any])?
            var runtimeError: Error?
            do {
                preparedRuntime = try self.prepareRuntime()
            } catch {
                runtimeError = error
            }
            DispatchQueue.main.async {
                guard generation == self.launchGeneration, !self.isTerminating else { return }
                guard let preparedRuntime = preparedRuntime else {
                    self.showFailure(
                        "The private local runtime could not be prepared.",
                        detail: runtimeError?.localizedDescription ?? "The bundled runtime is unavailable."
                    )
                    return
                }
                self.runtimeURL = preparedRuntime.0
                self.expectedBuildHash = preparedRuntime.1["buildHash"] as! String
                self.expectedFrontendHash = preparedRuntime.1["frontendIndexSha256"] as! String
                self.pythonURL = URL(fileURLWithPath: preparedRuntime.1["pythonExecutable"] as! String)
                self.expectedPythonVersion = preparedRuntime.1["pythonVersion"] as! String
                self.statusLabel.stringValue = "Checking the verified local service…"
                self.detailLabel.stringValue = "The service is available only on this Mac at 127.0.0.1."
                self.checkManifest { [weak self] ready, buildHash in
                    guard let self = self, generation == self.launchGeneration else { return }
                    if ready && allowReuse {
                        self.ownsServer = false
                        self.showReady(buildHash: buildHash, reused: true)
                    } else {
                        self.startServer(generation: generation)
                    }
                }
            }
        }
    }

    private func startServer(generation: Int) {
        guard let pythonURL = pythonURL, let runtimeURL = runtimeURL else { return }
        statusLabel.stringValue = "Starting the verified local server…"
        detailLabel.stringValue = "This usually takes a few seconds while the immutable local package is validated."

        do {
            port = try availableLoopbackPort(preferred: port)
            let logDirectory = logURL.deletingLastPathComponent()
            try FileManager.default.createDirectory(
                at: logDirectory,
                withIntermediateDirectories: true
            )
            if let size = try? logURL.resourceValues(forKeys: [.fileSizeKey]).fileSize,
               size > 5_000_000 {
                try Data().write(to: logURL, options: .atomic)
            } else if !FileManager.default.fileExists(atPath: logURL.path) {
                FileManager.default.createFile(atPath: logURL.path, contents: Data())
            }
            let handle = try FileHandle(forWritingTo: logURL)
            try handle.seekToEnd()
            if let marker = "\n\n=== Transcript Browser launch \(Date()) ===\n".data(using: .utf8) {
                try handle.write(contentsOf: marker)
            }
            serverLogHandle = handle

            let process = Process()
            process.executableURL = pythonURL
            // Finder-launched applications inherit a working directory inside the
            // Desktop/FileProvider tree. Python can block while resolving that
            // directory before our module is imported, so give the child a small,
            // stable runtime directory and pass the project path explicitly.
            process.currentDirectoryURL = URL(
                fileURLWithPath: NSTemporaryDirectory(),
                isDirectory: true
            )
            // Do not put the Desktop project on PYTHONPATH before the interpreter
            // has initialized its standard-library codecs. FileProvider can stall
            // that early path scan. Bootstrap from an argument, then add the
            // project only when Python is ready to import the application.
            let sitePackagesURL = runtimeURL
                .appendingPathComponent("site-packages", isDirectory: true)
            let bootstrap = """
            import os,runpy,sys; runtime,site_packages,project,port,version=sys.argv[1:6]; assert sys.version_info[:2]==tuple(map(int,version.split('.')[:2])), "Python version changed; reinstall the Mac launcher"; print(f"Python runtime ready: prefix={sys.prefix} cwd={os.getcwd()}",flush=True); sys.path[0:0]=[runtime,site_packages]; sys.argv=["backend.app.cli","--project-root",project,"--port",port]; runpy.run_module("backend.app.cli",run_name="__main__")
            """
            process.arguments = [
                "-I",
                "-S",
                "-B",
                "-c",
                bootstrap,
                runtimeURL.path,
                sitePackagesURL.path,
                runtimeURL.path,
                String(port),
                expectedPythonVersion,
            ]
            process.standardOutput = handle
            process.standardError = handle
            let inherited = ProcessInfo.processInfo.environment
            var environment: [String: String] = [:]
            for key in ["HOME", "TMPDIR", "USER", "LOGNAME"] {
                if let value = inherited[key] {
                    environment[key] = value
                }
            }
            environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
            environment["LANG"] = inherited["LANG"] ?? "C.UTF-8"
            environment["LC_CTYPE"] = inherited["LC_CTYPE"] ?? "C.UTF-8"
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONUNBUFFERED"] = "1"
            process.environment = environment
            process.terminationHandler = { [weak self] terminated in
                if let message = "Launcher child exited with code \(terminated.terminationStatus).\n".data(using: .utf8) {
                    try? handle.write(contentsOf: message)
                }
                DispatchQueue.main.async {
                    guard let self = self,
                          !self.isTerminating,
                          generation == self.launchGeneration else { return }
                    self.showFailure(
                        "The local server stopped.",
                        detail: "Exit code \(terminated.terminationStatus). Details are in \(self.logURL.path)."
                    )
                }
            }
            try process.run()
            serverProcess = process
            ownsServer = true
            readinessStarted = Date()
            pollUntilReady(generation: generation, attempt: 0)
        } catch {
            if let message = "Launcher failed to start child: \(error)\n".data(using: .utf8) {
                try? serverLogHandle?.write(contentsOf: message)
            }
            showFailure(
                "The local server could not be started.",
                detail: "\(error.localizedDescription) Log: \(logURL.path)"
            )
        }
    }

    private func availableLoopbackPort(preferred: Int) throws -> Int {
        let descriptor = socket(AF_INET, SOCK_STREAM, 0)
        guard descriptor >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        defer { Darwin.close(descriptor) }
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        func bindPort(_ value: Int) -> Int32 {
            address.sin_port = UInt16(value).bigEndian
            return withUnsafePointer(to: &address) { pointer in
                pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    Darwin.bind(descriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
        }
        if bindPort(preferred) != 0 && bindPort(0) != 0 {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
        }
        var size = socklen_t(MemoryLayout<sockaddr_in>.size)
        let result = withUnsafeMutablePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(descriptor, $0, &size)
            }
        }
        guard result == 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        return Int(UInt16(bigEndian: address.sin_port))
    }

    private func pollUntilReady(generation: Int, attempt: Int) {
        guard generation == launchGeneration, !isTerminating else { return }
        checkManifest { [weak self] ready, buildHash in
            guard let self = self, generation == self.launchGeneration else { return }
            if ready {
                self.showReady(buildHash: buildHash, reused: false)
                return
            }
            if Date().timeIntervalSince(self.readinessStarted) >= 90 {
                self.showFailure(
                    "The local server did not become ready within 90 seconds.",
                    detail: "Quit and try again. Details are in \(self.logURL.path)."
                )
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.pollUntilReady(generation: generation, attempt: attempt + 1)
            }
        }
    }

    private func checkManifest(completion: @escaping (Bool, String?) -> Void) {
        let origin = serverURL
        let expectedBuild = expectedBuildHash
        let expectedFrontend = expectedFrontendHash
        var request = URLRequest(url: manifestURL)
        request.timeoutInterval = 1.5
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let http = response as? HTTPURLResponse
            if http?.statusCode == 200,
               let data = data,
               let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let hash = object["buildHash"] as? String,
               hash == expectedBuild,
               object["scope"] as? String == "full",
               object["technicalPreview"] as? Bool == false,
               let capabilities = object["capabilities"] as? [String: Any],
               capabilities["pdfReports"] as? Bool == true {
                var frontendRequest = URLRequest(url: origin)
                frontendRequest.timeoutInterval = 1.5
                frontendRequest.cachePolicy = .reloadIgnoringLocalCacheData
                URLSession.shared.dataTask(with: frontendRequest) { html, response, _ in
                    let digest = html.map { SHA256.hash(data: $0).map { String(format: "%02x", $0) }.joined() }
                    let ready = (response as? HTTPURLResponse)?.statusCode == 200 && digest == expectedFrontend
                    DispatchQueue.main.async { completion(ready, ready ? hash : nil) }
                }.resume()
            } else {
                DispatchQueue.main.async { completion(false, nil) }
            }
        }.resume()
    }

    private func showReady(buildHash: String?, reused: Bool) {
        serverIsReady = true
        progress.stopAnimation(nil)
        progress.isHidden = true
        openButton.isEnabled = true
        retryButton.isHidden = true
        statusLabel.stringValue = reused
            ? "The local transcript browser is already running."
            : "The local transcript browser is ready."
        let shortHash = String((buildHash ?? "verified build").prefix(16))
        quitButton.title = ownsServer ? "Stop & Quit" : "Quit Launcher"
        let lifecycle = ownsServer
            ? "Closing this launcher stops the server it started."
            : "This launcher is using an already-running local server and will not stop it."
        detailLabel.stringValue = "Build \(shortHash) · \(serverURL.absoluteString)\n\(lifecycle)"
        if selfTest {
            let receipt: [String: Any] = ["passed": true, "buildHash": buildHash ?? "", "url": serverURL.absoluteString, "reused": reused, "ownedProcess": ownsServer]
            if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]), let output = String(data: data, encoding: .utf8) {
                print(output)
            }
            NSApp.terminate(nil)
        } else if !didOpenBrowser {
            didOpenBrowser = true
            NSWorkspace.shared.open(serverURL)
        }
    }

    private func showFailure(_ message: String, detail: String) {
        serverIsReady = false
        progress.stopAnimation(nil)
        progress.isHidden = true
        openButton.isEnabled = false
        retryButton.isHidden = false
        statusLabel.stringValue = message
        detailLabel.stringValue = detail
        if selfTest {
            exitCode = 1
            FileHandle.standardError.write(Data("Native launcher self-test failed: \(message) \(detail)\n".utf8))
            NSApp.terminate(nil)
        }
    }

    @objc private func openBrowser(_ sender: Any?) {
        guard serverIsReady else { return }
        NSWorkspace.shared.open(serverURL)
    }

    @objc private func retryLaunch(_ sender: Any?) {
        launchGeneration += 1
        let stoppedGeneration = launchGeneration
        let stopping = ownsServer ? serverProcess : nil
        if let process = stopping, process.isRunning {
            process.terminationHandler = nil
            process.terminate()
        }
        ownsServer = false
        serverProcess = nil
        try? serverLogHandle?.close()
        serverLogHandle = nil
        if let process = stopping, process.isRunning {
            statusLabel.stringValue = "Stopping the prior local server…"
            DispatchQueue.global(qos: .userInitiated).async {
                process.waitUntilExit()
                DispatchQueue.main.async {
                    guard stoppedGeneration == self.launchGeneration, !self.isTerminating else { return }
                    self.beginLaunch(allowReuse: false)
                }
            }
        } else {
            beginLaunch(allowReuse: stopping == nil)
        }
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.run()
Darwin.exit(delegate.exitCode)
