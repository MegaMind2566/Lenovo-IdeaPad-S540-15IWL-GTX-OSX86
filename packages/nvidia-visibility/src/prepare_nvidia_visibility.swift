// Prepare a private experimental EFI; never install it or write NVRAM.
import Foundation
import CoreFoundation
import CryptoKit
import Darwin

private let appleGUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
private let maximumFiles = 10_000
private let maximumBytes: Int64 = 512 * 1024 * 1024
private let maximumFileBytes: Int64 = 128 * 1024 * 1024

private struct PreparationError: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

private func require(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
    if try !condition() { throw PreparationError(message) }
}

private func exactBoolean(_ value: Any?, equals expected: Bool) -> Bool {
    guard let number = value as? NSNumber,
          CFGetTypeID(number) == CFBooleanGetTypeID() else { return false }
    return number.boolValue == expected
}

private func absoluteURL(_ path: String, directory: Bool) throws -> URL {
    try require(path.hasPrefix("/") && !path.unicodeScalars.contains(where: { $0.value == 0 }),
                "Paths must be absolute and contain no null characters.")
    let components = path.split(separator: "/", omittingEmptySubsequences: true)
    try require(!components.contains(".") && !components.contains(".."),
                "Paths must not contain dot or parent-directory components.")
    // Normalize separators lexically. standardizedFileURL also rewrites Darwin's
    // /private/var alias to /var, which would introduce a symbolic-link ancestor.
    let lexical = "/" + components.joined(separator: "/")
    return URL(fileURLWithPath: lexical, isDirectory: directory)
}

private func containsToken(_ arguments: String, _ token: String) throws -> Bool {
    let escaped = NSRegularExpression.escapedPattern(for: token)
    let expression = try NSRegularExpression(
        pattern: "(?<![^\\x09-\\x0D\\x20])" + escaped + "(?![^\\x09-\\x0D\\x20])")
    return expression.firstMatch(in: arguments, range: NSRange(arguments.startIndex..., in: arguments)) != nil
}

private func removeDisableToken(_ arguments: String) throws -> String {
    try require(!arguments.unicodeScalars.contains(where: { $0.value == 0 }), "The boot arguments contain a null character.")
    let valuedDisable = try NSRegularExpression(pattern: "(?<![^\\x09-\\x0D\\x20])-wegnoegpu=")
    try require(valuedDisable.firstMatch(in: arguments, range: NSRange(arguments.startIndex..., in: arguments)) == nil,
                "A valued -wegnoegpu argument is unsupported; the experiment only removes the exact bare token.")
    try require(try containsToken(arguments, "-wegnoegpu"), "The source does not contain the exact -wegnoegpu boot argument.")
    try require(try containsToken(arguments, "-igfxblr"), "The working -igfxblr panel argument is missing.")
    let expression = try NSRegularExpression(pattern: "(?<![^\\x09-\\x0D\\x20])-wegnoegpu(?![^\\x09-\\x0D\\x20])")
    let result = expression.stringByReplacingMatches(in: arguments,
        range: NSRange(arguments.startIndex..., in: arguments), withTemplate: "")
    try require(!(try containsToken(result, "-wegnoegpu")) && (try containsToken(result, "-igfxblr")),
                "The bounded boot-argument edit failed.")
    return result
}

private func propertyListsEqual(_ lhs: Any, _ rhs: Any) -> Bool {
    if let left = lhs as? [String: Any], let right = rhs as? [String: Any] {
        return left.count == right.count && left.allSatisfy { key, value in
            guard let other = right[key] else { return false }
            return propertyListsEqual(value, other)
        }
    }
    if let left = lhs as? [Any], let right = rhs as? [Any] {
        return left.count == right.count && zip(left, right).allSatisfy { propertyListsEqual($0.0, $0.1) }
    }
    if let left = lhs as? Data, let right = rhs as? Data { return left == right }
    if let left = lhs as? Date, let right = rhs as? Date { return left == right }
    if let left = lhs as? String, let right = rhs as? String { return left == right }
    if let left = lhs as? NSNumber, let right = rhs as? NSNumber {
        let leftBool = CFGetTypeID(left) == CFBooleanGetTypeID()
        let rightBool = CFGetTypeID(right) == CFBooleanGetTypeID()
        let leftReal = ["f", "d"].contains(String(cString: left.objCType))
        let rightReal = ["f", "d"].contains(String(cString: right.objCType))
        return leftBool == rightBool && leftReal == rightReal && left == right
    }
    return false
}

private func dictionary(from data: Data) throws -> [String: Any] {
    let value = try PropertyListSerialization.propertyList(from: data, options: [], format: nil)
    guard let result = value as? [String: Any] else { throw PreparationError("The configuration root is not a dictionary.") }
    return result
}

private func transformedConfiguration(_ original: [String: Any]) throws -> [String: Any] {
    guard var nvram = original["NVRAM"] as? [String: Any],
          var add = nvram["Add"] as? [String: Any],
          var apple = add[appleGUID] as? [String: Any],
          let arguments = apple["boot-args"] as? String,
          let delete = nvram["Delete"] as? [String: Any],
          let appleDelete = delete[appleGUID] as? [String] else {
        throw PreparationError("The source NVRAM boot-argument structure is unsupported.")
    }
    try require(appleDelete.contains("boot-args"),
                "The working source must already delete boot-args before adding its configured value.")
    try require(exactBoolean(nvram["WriteFlash"], equals: true), "The source WriteFlash setting is unsupported.")
    try require(exactBoolean(nvram["LegacyOverwrite"], equals: false), "The source LegacyOverwrite setting is unsupported.")
    if let legacy = nvram["LegacyEnable"] {
        try require(exactBoolean(legacy, equals: false), "Legacy NVRAM emulation is unsupported for this experiment.")
    }
    apple["boot-args"] = try removeDisableToken(arguments)
    add[appleGUID] = apple
    nvram["Add"] = add
    var result = original
    result["NVRAM"] = nvram

    // Restoring the single edited string must reproduce the entire original plist.
    var restoredApple = apple
    restoredApple["boot-args"] = arguments
    var restoredAdd = add
    restoredAdd[appleGUID] = restoredApple
    var restoredNVRAM = nvram
    restoredNVRAM["Add"] = restoredAdd
    var restored = result
    restored["NVRAM"] = restoredNVRAM
    try require(propertyListsEqual(restored, original), "An unrelated configuration value would change.")
    return result
}

private func statWithoutLinks(_ url: URL) throws -> stat {
    var information = stat()
    guard lstat(url.path, &information) == 0 else { throw PreparationError("A required path cannot be inspected: " + url.path) }
    try require((information.st_mode & S_IFMT) != S_IFLNK, "Symbolic links are unsupported: " + url.path)
    return information
}

private func plainDirectory(_ url: URL) throws {
    let information = try statWithoutLinks(url)
    try require((information.st_mode & S_IFMT) == S_IFDIR, "A required directory is unavailable: " + url.path)
}

private func checkAncestors(_ url: URL) throws {
    var current = URL(fileURLWithPath: "/", isDirectory: true)
    for component in url.pathComponents.dropFirst() {
        current.appendPathComponent(component)
        try plainDirectory(current)
    }
}

private func readPlainFile(_ url: URL, limit: Int64 = maximumFileBytes) throws -> Data {
    let descriptor = open(url.path, O_RDONLY | O_NOFOLLOW)
    guard descriptor >= 0 else { throw PreparationError("A source file cannot be opened: " + url.path) }
    defer { close(descriptor) }
    var information = stat()
    try require(fstat(descriptor, &information) == 0 && (information.st_mode & S_IFMT) == S_IFREG,
                "A source entry is not a regular file: " + url.path)
    try require(information.st_nlink == 1, "Hard-linked source files are unsupported: " + url.path)
    try require(information.st_size >= 0 && information.st_size <= limit, "A source file exceeds the size limit: " + url.path)
    var result = Data()
    var buffer = [UInt8](repeating: 0, count: 1024 * 1024)
    while true {
        let count = buffer.withUnsafeMutableBytes { storage in
            Darwin.read(descriptor, storage.baseAddress, storage.count)
        }
        if count < 0 {
            if errno == EINTR { continue }
            throw PreparationError("A source file could not be read: " + url.path)
        }
        if count == 0 { break }
        try require(Int64(result.count) + Int64(count) <= limit, "A source file grew beyond the size limit.")
        result.append(contentsOf: buffer.prefix(count))
    }
    var finalInformation = stat()
    try require(fstat(descriptor, &finalInformation) == 0 && information.st_size == finalInformation.st_size &&
                information.st_ino == finalInformation.st_ino && Int64(result.count) == information.st_size,
                "A source file changed while it was being read.")
    return result
}

private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

private struct Snapshot: Equatable {
    var files: [String: String] = [:]
    var directories: Set<String> = []
}

private func snapshot(_ root: URL) throws -> Snapshot {
    try plainDirectory(root)
    var result = Snapshot()
    var bytes: Int64 = 0
    var entries = 0
    var foldedPaths: Set<String> = []
    func visit(_ directory: URL, relative: String, depth: Int) throws {
        try require(depth <= 64, "The EFI directory nesting exceeds the limit.")
        let children = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        for child in children.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
            entries += 1
            try require(entries <= maximumFiles, "The EFI contains too many entries.")
            let name = child.lastPathComponent
            try require(!name.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }),
                        "An EFI path contains control characters.")
            let path = relative.isEmpty ? name : relative + "/" + name
            try require(foldedPaths.insert(path.precomposedStringWithCanonicalMapping.lowercased()).inserted,
                        "EFI paths collide when copied to a case-insensitive filesystem.")
            let information = try statWithoutLinks(child)
            switch information.st_mode & S_IFMT {
            case S_IFDIR:
                result.directories.insert(path)
                try visit(child, relative: path, depth: depth + 1)
            case S_IFREG:
                try require(information.st_size >= 0 && information.st_size <= maximumFileBytes,
                            "An EFI file exceeds the 128 MB preparation limit.")
                bytes += information.st_size
                try require(bytes >= 0 && bytes <= maximumBytes, "The EFI exceeds the 512 MB preparation limit.")
                result.files[path] = digest(try readPlainFile(child))
            default:
                throw PreparationError("The EFI contains an unsupported filesystem entry: " + path)
            }
        }
    }
    try visit(root, relative: "", depth: 0)
    return result
}

private func manifest(_ snapshot: Snapshot) -> Data {
    let directories = snapshot.directories.sorted().map { "D\t" + $0 + "\n" }.joined()
    let files = snapshot.files.keys.sorted().map { snapshot.files[$0]! + "  " + $0 + "\n" }.joined()
    return Data((directories + files).utf8)
}

private func writeNew(_ data: Data, to url: URL) throws {
    try data.write(to: url, options: [.withoutOverwriting])
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
}

private func validate(_ configuration: URL, using validator: URL, log: URL) throws {
    let created = FileManager.default.createFile(atPath: log.path, contents: Data(), attributes: [.posixPermissions: 0o600])
    try require(created, "A private validation log could not be created.")
    let handle = try FileHandle(forWritingTo: log)
    defer { try? handle.close() }
    let process = Process()
    process.executableURL = validator
    process.arguments = [configuration.path]
    process.standardOutput = handle
    process.standardError = handle
    try process.run()
    process.waitUntilExit()
    try require(process.terminationReason == .exit && process.terminationStatus == 0,
                "OpenCore validation failed. Read the private log: " + log.path)
}

private func stage(source: URL, parent: URL, validator: URL) throws -> URL {
    try checkAncestors(source)
    try checkAncestors(parent)
    try require(source.path != parent.path && !parent.path.hasPrefix(source.path + "/") &&
                !source.path.hasPrefix(parent.path + "/"), "The source EFI and output parent must not overlap.")
    try plainDirectory(source.appendingPathComponent("BOOT"))
    try plainDirectory(source.appendingPathComponent("OC"))
    let before = try snapshot(source)
    for required in ["BOOT/BOOTx64.efi", "OC/OpenCore.efi", "OC/config.plist"] {
        try require(before.files[required] != nil, "A required EFI file is missing: " + required)
        try require(!(try readPlainFile(source.appendingPathComponent(required))).isEmpty, "A required EFI file is empty: " + required)
    }
    let originalData = try readPlainFile(source.appendingPathComponent("OC/config.plist"), limit: 4 * 1024 * 1024)
    let original = try dictionary(from: originalData)
    let candidate = try transformedConfiguration(original)
    let candidateData = try PropertyListSerialization.data(fromPropertyList: candidate, format: .xml, options: 0)
    try require(propertyListsEqual(candidate, try dictionary(from: candidateData)), "The edited configuration did not survive serialization.")
    let validatorInfo = try statWithoutLinks(validator)
    try require((validatorInfo.st_mode & S_IFMT) == S_IFREG && access(validator.path, X_OK) == 0,
                "The packaged OpenCore validator is not executable.")

    let output = parent.appendingPathComponent("NVIDIA-VISIBILITY." + UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: output, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
    do {
        try writeNew(originalData, to: output.appendingPathComponent("original-config.plist"))
        try writeNew(manifest(before), to: output.appendingPathComponent("source-before.sha256"))
        try validate(source.appendingPathComponent("OC/config.plist"), using: validator,
                     log: output.appendingPathComponent("baseline-ocvalidate.txt"))
        let efi = output.appendingPathComponent("EFI", isDirectory: true)
        try FileManager.default.createDirectory(at: efi, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        func selected(_ path: String) -> Bool { path == "BOOT" || path == "OC" || path.hasPrefix("BOOT/") || path.hasPrefix("OC/") }
        let selectedDirectories = before.directories.filter(selected)
        for path in selectedDirectories.sorted(by: { $0.count == $1.count ? $0 < $1 : $0.count < $1.count }) {
            try FileManager.default.createDirectory(at: efi.appendingPathComponent(path), withIntermediateDirectories: false,
                                                   attributes: [.posixPermissions: 0o700])
        }
        var expectedFiles: [String: String] = [:]
        for path in before.files.keys.filter(selected).sorted() {
            let data = try readPlainFile(source.appendingPathComponent(path))
            try require(digest(data) == before.files[path], "The source EFI changed during copying.")
            let copied = path == "OC/config.plist" ? candidateData : data
            try writeNew(copied, to: efi.appendingPathComponent(path))
            expectedFiles[path] = digest(copied)
        }
        let staged = try snapshot(efi)
        try require(staged.files == expectedFiles && staged.directories == selectedDirectories,
                    "The staged EFI differs from the bounded copy.")
        try require(propertyListsEqual(candidate, try dictionary(from: readPlainFile(efi.appendingPathComponent("OC/config.plist")))),
                    "The staged configuration differs from the verified edit.")
        try validate(efi.appendingPathComponent("OC/config.plist"), using: validator,
                     log: output.appendingPathComponent("candidate-ocvalidate.txt"))
        let after = try snapshot(source)
        try writeNew(manifest(after), to: output.appendingPathComponent("source-after.sha256"))
        try require(before == after, "The source EFI changed during preparation. Do not use this candidate.")
        try writeNew(manifest(staged), to: output.appendingPathComponent("candidate.sha256"))
        let note = """
        Private NVIDIA visibility experiment

        The source EFI and NVRAM were not modified by this program.
        The candidate contains only the source BOOT and OC directories.
        Only exact -wegnoegpu boot-argument tokens were removed from config.plist.
        The original -igfxblr argument and all other plist values were preserved.
        Both configurations passed the packaged OpenCore 1.0.8 validator.

        Keep the original Samsung EFI available as the fallback boot path.
        Its existing Delete/Add boot-args settings restore the baseline arguments
        when that original OpenCore configuration is selected again.
        Booting the candidate will apply its configured boot-args through the
        existing NVRAM Delete/Add policy; preparation itself does not apply them.
        This folder includes private machine configuration. Do not publish it.

        READY: preparation completed; no boot medium has been changed.

        """
        try writeNew(Data(note.utf8), to: output.appendingPathComponent("README.txt"))
        try writeNew(Data("Prepared. No EFI installation or NVRAM write was performed.\n".utf8), to: output.appendingPathComponent("READY.txt"))
        return output
    } catch {
        try? writeNew(Data(("Preparation failed. Do not boot this candidate.\n" + String(describing: error) + "\n").utf8),
                      to: output.appendingPathComponent("FAILED.txt"))
        throw error
    }
}

private func fixtures() throws {
    try require(try absoluteURL("/private/var/fixture/source", directory: true).path == "/private/var/fixture/source",
                "The canonical Darwin private path was rewritten.")
    for path in ["relative/path", "/private/var/../var/fixture", "/private/./var/fixture"] {
        var rejected = false
        do { _ = try absoluteURL(path, directory: true) } catch { rejected = true }
        try require(rejected, "A noncanonical path fixture was accepted.")
    }
    func configuration(_ arguments: String = "-v -wegnoegpu -igfxblr debug=0x100") -> [String: Any] {
        return ["NVRAM": ["Add": [appleGUID: ["boot-args": arguments, "csr-active-config": Data([3, 0, 0, 0])]],
                          "Delete": [appleGUID: ["boot-args", "csr-active-config"]],
                          "WriteFlash": true, "LegacyOverwrite": false],
                "ACPI": ["Add": [["Enabled": true, "Path": "SSDT-PLUG.aml"]]],
                "DeviceProperties": ["Add": ["PciRoot(0x0)/Pci(0x2,0x0)": ["framebuffer-patch-enable": Data([1, 0, 0, 0])]]],
                "PlatformInfo": ["Generic": ["SystemProductName": "FixtureModel"]]]
    }
    func arguments(_ value: [String: Any]) -> String {
        let nvram = value["NVRAM"] as! [String: Any]
        let add = nvram["Add"] as! [String: Any]
        return (add[appleGUID] as! [String: Any])["boot-args"] as! String
    }
    for input in ["-wegnoegpu -igfxblr", "-igfxblr\t-wegnoegpu  -wegnoegpu -v", "-v -igfxblr -wegnoegpu"] {
        let base = configuration(input)
        let edited = try transformedConfiguration(base)
        try require(!(try containsToken(arguments(edited), "-wegnoegpu")), "A removal fixture failed.")
        let encoded = try PropertyListSerialization.data(fromPropertyList: edited, format: .xml, options: 0)
        try require(propertyListsEqual(edited, try dictionary(from: encoded)), "A serialization fixture failed.")
    }
    let spacing = try transformedConfiguration(configuration("-v\t-wegnoegpu  -igfxblr foo-wegnoegpu=1"))
    try require(arguments(spacing) == "-v\t  -igfxblr foo-wegnoegpu=1", "Unrelated whitespace or an argument prefix changed.")
    for input in ["-igfxblr -wegnoegpu=1", "-igfxblr -wegnoegpu -wegnoegpu=1", "-igfxblr x-wegnoegpu", "-wegnoegpu"] {
        do { _ = try transformedConfiguration(configuration(input)); throw PreparationError("A missing-flag fixture was accepted.") }
        catch let error as PreparationError {
            try require(error.description != "A missing-flag fixture was accepted.", error.description)
        }
    }
    for key in ["Delete", "WriteFlash", "LegacyOverwrite"] {
        var base = configuration()
        var nvram = base["NVRAM"] as! [String: Any]
        if key == "Delete" { nvram[key] = [appleGUID: ["csr-active-config"]] }
        else if key == "WriteFlash" { nvram[key] = false }
        else { nvram[key] = true }
        base["NVRAM"] = nvram
        var rejected = false
        do { _ = try transformedConfiguration(base) } catch { rejected = true }
        try require(rejected, "An unsupported NVRAM-policy fixture was accepted.")
    }
    try require(!propertyListsEqual(["Value": true], ["Value": 1]), "Boolean and integer values were conflated.")
    print("NVIDIA visibility transformation fixtures passed.")
}

do {
    umask(0o077)
    if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
        try fixtures()
    } else {
        try require(CommandLine.arguments.count == 4,
                    "Usage: prepare-nvidia-visibility SOURCE_EFI_DIRECTORY OUTPUT_PARENT OCVALIDATE_PATH")
        let source = try absoluteURL(CommandLine.arguments[1], directory: true)
        let parent = try absoluteURL(CommandLine.arguments[2], directory: true)
        let validator = try absoluteURL(CommandLine.arguments[3], directory: false)
        let output = try stage(source: source, parent: parent, validator: validator)
        print("Experimental EFI prepared: " + output.appendingPathComponent("EFI").path)
        print("Private reference and validation logs: " + output.path)
        print("The original EFI and NVRAM are unchanged. No boot medium has been modified.")
    }
} catch {
    fputs("NVIDIA visibility preparation stopped: " + String(describing: error) + "\n", stderr)
    exit(1)
}
