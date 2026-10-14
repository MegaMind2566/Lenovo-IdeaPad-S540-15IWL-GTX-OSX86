import Foundation
import CoreFoundation

// Locate the EFI partition associated with the running external APFS Data volume.
// This association does not independently prove which EFI firmware booted.
// All diskutil invocations are read-only. Mounting is the caller's responsibility.
private struct LocateError: Error {
    let message: String
    init(_ message: String) { self.message = message }
}

private typealias Plist = [String: Any]
private typealias DiskQuery = ([String]) throws -> Plist
private let dataPath = "/System/Volumes/Data"

private func requiredString(_ plist: Plist, _ key: String) throws -> String {
    guard let value = plist[key] as? String, !value.isEmpty else {
        throw LocateError("A required disk metadata field is missing: \(key).")
    }
    return value
}

private func requiredBool(_ plist: Plist, _ key: String) throws -> Bool {
    guard let value = plist[key] as? NSNumber,
          CFGetTypeID(value) == CFBooleanGetTypeID() else {
        throw LocateError("A disk metadata Boolean is missing or invalid: \(key).")
    }
    return value.boolValue
}

private func matches(_ text: String, _ pattern: String) -> Bool {
    return text.range(of: pattern, options: .regularExpression) != nil
}

private func wholeID(_ value: String) -> Bool {
    return matches(value, "^disk[0-9]+$")
}

private func partitionID(_ value: String, on whole: String) -> Bool {
    return wholeID(whole) && matches(value, "^" + whole + "s[0-9]+$")
}

private func partitionUUID(_ plist: Plist) throws -> String {
    let value = try requiredString(plist, "DiskUUID")
    guard matches(value, "^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$") else {
        throw LocateError("The EFI partition has no valid stable partition UUID.")
    }
    return value.uppercased()
}

private struct Mapping {
    let container: String
    let physicalStore: String
    let wholeDisk: String
    let efiPartition: String
    let efiPartitionUUID: String
    let mounted: Bool
    let mountPoint: String?

    var json: Plist {
        return [
            "format": 1,
            "status": "mapped",
            "container": container,
            "physicalStore": physicalStore,
            "wholeDisk": wholeDisk,
            "efiPartition": efiPartition,
            "efiPartitionUUID": efiPartitionUUID,
            "mounted": mounted,
            "mountPoint": mountPoint.map { $0 as Any } ?? NSNull()
        ]
    }
}

private func locateEFI(query: DiskQuery) throws -> Mapping {
    let data = try query(["info", "-plist", dataPath])
    let container = try requiredString(data, "APFSContainerReference")
    let dataIdentifier = try requiredString(data, "DeviceIdentifier")
    guard wholeID(container), partitionID(dataIdentifier, on: container),
          try requiredBool(data, "Mounted"),
          try requiredString(data, "MountPoint") == dataPath else {
        throw LocateError("The running Data volume has no unambiguous APFS mapping.")
    }

    let apfs = try query(["apfs", "list", "-plist", container])
    guard let containers = apfs["Containers"] as? [Plist], containers.count == 1,
          try requiredString(containers[0], "ContainerReference") == container,
          let stores = containers[0]["PhysicalStores"] as? [Plist], stores.count == 1 else {
        throw LocateError("The running APFS container must have exactly one physical store.")
    }
    let physicalStore = try requiredString(stores[0], "DeviceIdentifier")
    guard matches(physicalStore, "^disk[0-9]+s[0-9]+$") else {
        throw LocateError("The APFS physical-store identifier is invalid.")
    }
    let store = try query(["info", "-plist", physicalStore])
    let wholeDisk = try requiredString(store, "ParentWholeDisk")
    guard partitionID(physicalStore, on: wholeDisk),
          try requiredString(store, "DeviceIdentifier") == physicalStore,
          try requiredString(store, "APFSContainerReference") == container,
          try requiredString(store, "Content") == "Apple_APFS",
          try !requiredBool(store, "WholeDisk") else {
        throw LocateError("The APFS physical-store identity is inconsistent.")
    }

    let whole = try query(["info", "-plist", wholeDisk])
    guard try requiredString(whole, "DeviceIdentifier") == wholeDisk,
          try requiredString(whole, "Content") == "GUID_partition_scheme",
          try requiredBool(whole, "WholeDisk"),
          try !requiredBool(whole, "Internal") else {
        throw LocateError("The running APFS store is not on an external GPT disk.")
    }
    if let kind = whole["VirtualOrPhysical"] as? String, kind != "Physical" {
        throw LocateError("The running APFS store is not on a physical disk.")
    }

    let listing = try query(["list", "-plist", wholeDisk])
    guard let disks = listing["AllDisksAndPartitions"] as? [Plist], disks.count == 1,
          try requiredString(disks[0], "DeviceIdentifier") == wholeDisk,
          try requiredString(disks[0], "Content") == "GUID_partition_scheme",
          let partitions = disks[0]["Partitions"] as? [Plist] else {
        throw LocateError("The external GPT partition listing is ambiguous.")
    }
    var identifiers = Set<String>()
    for partition in partitions {
        let identifier = try requiredString(partition, "DeviceIdentifier")
        guard partitionID(identifier, on: wholeDisk), identifiers.insert(identifier).inserted else {
            throw LocateError("The external GPT contains inconsistent partition identifiers.")
        }
    }
    let listedStores = partitions.filter {
        ($0["DeviceIdentifier"] as? String) == physicalStore && ($0["Content"] as? String) == "Apple_APFS"
    }
    let efiPartitions = partitions.filter { ($0["Content"] as? String) == "EFI" }
    guard listedStores.count == 1, efiPartitions.count == 1 else {
        throw LocateError("The running external disk must contain one identifiable EFI partition.")
    }
    let efiPartition = try requiredString(efiPartitions[0], "DeviceIdentifier")
    let efi = try query(["info", "-plist", efiPartition])
    let uuid = try partitionUUID(efi)
    guard try requiredString(efi, "DeviceIdentifier") == efiPartition,
          try requiredString(efi, "ParentWholeDisk") == wholeDisk,
          try requiredString(efi, "Content") == "EFI",
          try !requiredBool(efi, "WholeDisk"),
          try !requiredBool(efi, "Internal") else {
        throw LocateError("The EFI partition does not match the running external disk.")
    }
    if let filesystem = efi["FilesystemType"] as? String, filesystem != "msdos" {
        throw LocateError("The EFI partition does not have the expected FAT filesystem.")
    }

    let mounted = try requiredBool(efi, "Mounted")
    var mountPoint: String? = nil
    if mounted {
        let point = try requiredString(efi, "MountPoint")
        let canonical = URL(fileURLWithPath: point, isDirectory: true)
            .resolvingSymlinksInPath().standardizedFileURL.path
        guard point.hasPrefix("/Volumes/"), point.count > "/Volumes/".count,
              point == canonical, !point.contains("\n"), !point.contains("\r") else {
            throw LocateError("The EFI mount point is not a canonical volume path.")
        }
        let mountedInfo = try query(["info", "-plist", point])
        guard try requiredString(mountedInfo, "DeviceIdentifier") == efiPartition,
              try requiredString(mountedInfo, "ParentWholeDisk") == wholeDisk,
              try requiredString(mountedInfo, "Content") == "EFI",
              try requiredBool(mountedInfo, "Mounted"),
              try requiredString(mountedInfo, "MountPoint") == point,
              try partitionUUID(mountedInfo) == uuid else {
            throw LocateError("The mounted EFI path has a different partition identity.")
        }
        mountPoint = point
    }
    return Mapping(container: container, physicalStore: physicalStore, wholeDisk: wholeDisk,
                   efiPartition: efiPartition, efiPartitionUUID: uuid,
                   mounted: mounted, mountPoint: mountPoint)
}

private func queryDiskutil(_ arguments: [String]) throws -> Plist {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/sbin/diskutil")
    process.arguments = arguments
    process.environment = ["LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"]
    let output = Pipe()
    process.standardOutput = output
    process.standardError = FileHandle.nullDevice
    do { try process.run() } catch { throw LocateError("The disk metadata query could not start.") }
    let bytes = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    guard process.terminationStatus == 0, !bytes.isEmpty, bytes.count <= 16 * 1024 * 1024 else {
        throw LocateError("The disk metadata query failed.")
    }
    guard let plist = try? PropertyListSerialization.propertyList(from: bytes, options: [], format: nil),
          let dictionary = plist as? Plist else {
        throw LocateError("The disk metadata query did not return a valid property list.")
    }
    return dictionary
}

private func writeJSON(_ object: Plist) {
    do {
        let bytes = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        FileHandle.standardOutput.write(bytes)
        FileHandle.standardOutput.write(Data([10]))
    } catch {
        FileHandle.standardError.write(Data("EFI locator: JSON serialization failed.\n".utf8))
        exit(1)
    }
}

private func selfTest() throws {
    let container = "disk14", whole = "disk8", store = "disk8s3", efi = "disk8s1"
    let point = "/Volumes/NVIDIA-LOCATOR-FIXTURE"
    let uuid = "12345678-1234-1234-1234-1234567890AB"
    func key(_ arguments: [String]) -> String { return arguments.joined(separator: "\t") }
    let dataKey = key(["info", "-plist", dataPath])
    let apfsKey = key(["apfs", "list", "-plist", container])
    let storeKey = key(["info", "-plist", store])
    let wholeKey = key(["info", "-plist", whole])
    let listKey = key(["list", "-plist", whole])
    let efiKey = key(["info", "-plist", efi])
    var base: [String: Plist] = [
        dataKey: ["APFSContainerReference": container, "DeviceIdentifier": "disk14s2",
                  "Mounted": true, "MountPoint": dataPath],
        apfsKey: ["Containers": [["ContainerReference": container,
                    "PhysicalStores": [["DeviceIdentifier": store]]]]],
        storeKey: ["DeviceIdentifier": store, "ParentWholeDisk": whole,
                   "APFSContainerReference": container, "Content": "Apple_APFS", "WholeDisk": false],
        wholeKey: ["DeviceIdentifier": whole, "Content": "GUID_partition_scheme",
                   "Internal": false, "WholeDisk": true, "VirtualOrPhysical": "Physical"],
        listKey: ["AllDisksAndPartitions": [["DeviceIdentifier": whole,
                    "Content": "GUID_partition_scheme", "Partitions": [
                    ["DeviceIdentifier": efi, "Content": "EFI"],
                    ["DeviceIdentifier": "disk8s2", "Content": "Microsoft Basic Data"],
                    ["DeviceIdentifier": store, "Content": "Apple_APFS"]]]]],
        efiKey: ["DeviceIdentifier": efi, "ParentWholeDisk": whole, "Content": "EFI",
                 "Internal": false, "WholeDisk": false, "Mounted": false,
                 "DiskUUID": uuid, "FilesystemType": "msdos"]
    ]
    func run(_ fixtures: [String: Plist]) throws -> Mapping {
        return try locateEFI { arguments in
            guard let answer = fixtures[key(arguments)] else {
                throw LocateError("A fixture query was unexpected.")
            }
            return answer
        }
    }
    func require(_ condition: Bool, _ message: String) throws {
        if !condition { throw LocateError("EFI locator self-test failed: " + message) }
    }
    var checks = 0
    func rejects(_ fixtures: [String: Plist], _ message: String) throws {
        do { _ = try run(fixtures) } catch { checks += 1; return }
        throw LocateError("EFI locator self-test accepted " + message)
    }
    let unmounted = try run(base)
    try require(unmounted.efiPartition == efi && unmounted.wholeDisk == whole &&
                unmounted.physicalStore == store && unmounted.container == container &&
                unmounted.efiPartitionUUID == uuid && unmounted.mountPoint == nil && !unmounted.mounted,
                "unmounted external mapping")
    try require(unmounted.json["mountPoint"] is NSNull, "null unmounted path")
    checks += 1
    var mounted = base
    mounted[efiKey]!["Mounted"] = true
    mounted[efiKey]!["MountPoint"] = point
    mounted[key(["info", "-plist", point])] = mounted[efiKey]
    let result = try run(mounted)
    try require(result.mounted && result.mountPoint == point && result.efiPartitionUUID == uuid,
                "mounted external mapping")
    checks += 1
    var optional = base
    optional[wholeKey]!.removeValue(forKey: "VirtualOrPhysical")
    optional[efiKey]!.removeValue(forKey: "FilesystemType")
    _ = try run(optional)
    checks += 1
    var bad = base
    bad[wholeKey]!["Internal"] = true
    try rejects(bad, "an internal disk")
    bad = base; bad[wholeKey]!["VirtualOrPhysical"] = "Virtual"
    try rejects(bad, "a virtual disk")
    bad = base; bad[wholeKey]!["Internal"] = 0
    try rejects(bad, "an integer masquerading as a Boolean")
    bad = base; bad[storeKey]!["ParentWholeDisk"] = "disk9"
    try rejects(bad, "a mismatched physical store parent")
    bad = base; bad[storeKey]!["APFSContainerReference"] = "disk15"
    try rejects(bad, "a mismatched physical store container")
    bad = base; bad[dataKey]!["Mounted"] = false
    try rejects(bad, "an unmounted Data volume")
    bad = base; bad[dataKey]!["DeviceIdentifier"] = "disk15s2"
    try rejects(bad, "a Data volume on a different container")
    bad = base; bad[apfsKey] = ["Containers": [["ContainerReference": container,
             "PhysicalStores": [["DeviceIdentifier": store], ["DeviceIdentifier": "disk9s2"]]]]]
    try rejects(bad, "multiple physical stores")
    bad = base; bad[apfsKey] = ["Containers": []]
    try rejects(bad, "a missing APFS container")
    bad = base; bad[apfsKey] = ["Containers": [["ContainerReference": container,
             "PhysicalStores": [["DeviceIdentifier": store]]], ["ContainerReference": "disk15"]]]
    try rejects(bad, "multiple APFS containers")
    bad = base; bad[efiKey]!["ParentWholeDisk"] = "disk9"
    try rejects(bad, "an EFI on a different disk")
    bad = base; bad[efiKey]!["DiskUUID"] = "not-a-uuid"
    try rejects(bad, "an invalid EFI UUID")
    bad = base; bad[efiKey]!["FilesystemType"] = "apfs"
    try rejects(bad, "a non-FAT EFI")
    bad = mounted; bad[key(["info", "-plist", point])]!["DiskUUID"] = "22345678-1234-1234-1234-1234567890AB"
    try rejects(bad, "a replaced mounted EFI")
    bad = mounted; bad[efiKey]!["MountPoint"] = "/Volumes/../tmp/EFI"
    try rejects(bad, "a noncanonical mount path")
    bad = mounted; bad[key(["info", "-plist", point])]!["DeviceIdentifier"] = "disk9s1"
    try rejects(bad, "a mounted path on a different partition")
    bad = base; bad[listKey] = ["AllDisksAndPartitions": [["DeviceIdentifier": whole,
        "Content": "GUID_partition_scheme", "Partitions": [
        ["DeviceIdentifier": efi, "Content": "EFI"], ["DeviceIdentifier": "disk8s2", "Content": "EFI"],
        ["DeviceIdentifier": store, "Content": "Apple_APFS"]]]]]
    try rejects(bad, "multiple EFI partitions")
    bad = base; bad[listKey] = ["AllDisksAndPartitions": [["DeviceIdentifier": whole,
        "Content": "GUID_partition_scheme", "Partitions": [["DeviceIdentifier": store, "Content": "Apple_APFS"]]]]]
    try rejects(bad, "a disk with no EFI partition")
    bad = base; bad[listKey] = ["AllDisksAndPartitions": [["DeviceIdentifier": whole,
        "Content": "GUID_partition_scheme", "Partitions": [
        ["DeviceIdentifier": efi, "Content": "EFI"], ["DeviceIdentifier": efi, "Content": "Microsoft Basic Data"],
        ["DeviceIdentifier": store, "Content": "Apple_APFS"]]]]]
    try rejects(bad, "duplicate partition identifiers")
    base.removeValue(forKey: efiKey)
    try rejects(base, "a failed EFI metadata query")
    print("EFI locator fixture checks passed (\(checks) cases).")
}

let arguments = Array(CommandLine.arguments.dropFirst())
do {
    if arguments == ["--self-test"] {
        try selfTest()
    } else if arguments == ["--locate-json"] {
        #if os(macOS)
        writeJSON(try locateEFI(query: queryDiskutil).json)
        #else
        throw LocateError("The EFI locator requires macOS.")
        #endif
    } else {
        throw LocateError("Usage: locate-efi --locate-json | --self-test")
    }
} catch {
    let message = (error as? LocateError)?.message ?? "EFI discovery failed."
    writeJSON(["format": 1, "status": "unavailable", "error": message])
    exit(1)
}
