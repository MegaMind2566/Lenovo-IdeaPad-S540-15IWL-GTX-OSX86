/* Pure numeric trace parser + macOS JavaScript for Automation entry point. */
var S540Trace = (function () {
    "use strict";
    var IDS = ["Fn-F5", "direct-F4", "direct-F7", "direct-F8", "direct-F9", "ordinary-Command-L"];
    var MAX_RECORDS = 128, MAX_INPUT = 4 * 1024 * 1024;
    function finite(n) { return typeof n === "number" && isFinite(n); }
    function integer(n) { return finite(n) && Math.floor(n) === n; }
    function prefixOK(s) { return typeof s === "string" && /^[A-Za-z0-9_. -]{1,80}$/.test(s); }
    function escaped(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
    function unixDecimal(value) {
        if ((typeof value !== "string" && typeof value !== "number") || (typeof value === "number" && !finite(value))) return null;
        var m = /^([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$/.exec(String(value));
        if (!m) return null;
        var digits = m[1] + (m[2] || ""), point = m[1].length + Number(m[3] || 0);
        if (point < -9 || point > 12) return null;
        while (point < 0) { digits = "0" + digits; point++; }
        while (digits.length < point) digits += "0";
        var whole = point ? digits.slice(0, point) : "0", fraction = digits.slice(point);
        if (fraction.length > 9 && /[1-9]/.test(fraction.slice(9))) return null;
        fraction = (fraction + "000000000").slice(0, 9);
        var seconds = Number(whole), nanos = Number(fraction);
        if (!integer(seconds) || seconds < 0 || seconds > 253402300799) return null;
        return {seconds: seconds, nanos: nanos};
    }
    function sourceTimestamp(value) {
        if (typeof value !== "string" || value.length > 64) return null;
        var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:?\d{2})$/.exec(value);
        if (!m) return null;
        var y = +m[1], mo = +m[2], d = +m[3], h = +m[4], mi = +m[5], se = +m[6];
        if (y < 1970 || mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || se > 59) return null;
        var ms = Date.UTC(y, mo - 1, d, h, mi, se), date = new Date(ms);
        if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d || date.getUTCHours() !== h || date.getUTCMinutes() !== mi || date.getUTCSeconds() !== se) return null;
        var zone = m[8], offset = 0;
        if (zone !== "Z") {
            var z = zone.replace(":", ""), zh = +z.slice(1, 3), zm = +z.slice(3, 5);
            if (zh > 23 || zm > 59) return null;
            offset = (zh * 3600 + zm * 60) * (z.charAt(0) === "+" ? 1 : -1);
        }
        return {seconds: ms / 1000 - offset, nanos: Number(((m[7] || "") + "000000000").slice(0, 9))};
    }
    function compare(a, b) { return a.seconds === b.seconds ? a.nanos - b.nanos : a.seconds - b.seconds; }
    function deltaSeconds(a, b) { return a.seconds - b.seconds + (a.nanos - b.nanos) / 1000000000; }
    function inWindow(time, start, end) { return compare(time, start) >= 0 && compare(time, end) < 0; }
    function scanOK(n, raw) {
        // Raw indexes have the break bit masked; custom mapped outputs may use the full byte.
        // Internal index 100 is printed literally because the source uses >256, not >=256.
        return (n >= 0 && n <= (raw ? 0x7f : 0xff)) || n === 0x100 ||
            (n >= 0xe001 && n <= (raw ? 0xe07f : 0xe0ff));
    }
    function message(text, prefix) {
        if (!prefixOK(prefix) || typeof text !== "string" || text.length > 256) return null;
        var re = new RegExp("^" + escaped(prefix) + ": sending key ([0-9a-f]{1,4})=([0-9a-f]{1,4})(?:, ([0-9a-f]{1,4})=([0-9a-f]{1,4}))? (down|up)\\n?$");
        var m = re.exec(text);
        if (!m || m[0].length !== text.length) return null;
        var raw = parseInt(m[1], 16), remapped = m[3] !== undefined;
        var mapped = remapped ? parseInt(m[2], 16) : raw;
        var adb = parseInt(remapped ? m[4] : m[2], 16);
        if (!scanOK(raw, true) || !scanOK(mapped, false) || adb > 255 || (remapped && mapped !== parseInt(m[3], 16))) return null;
        return {raw_scan: raw, mapped_scan: mapped, adb_code: adb, down: m[5] === "down"};
    }
    function knownLogHeader(text) {
        // log may canonicalize eventMessage to composedMessage in the displayed predicate.
        return /^Filtering the log data using (["'])(?:eventMessage|composedMessage) CONTAINS (["'])sending key\2\1$/.test(text);
    }
    function lines(text, allowLogHeader) {
        if (typeof text !== "string" || text.length > MAX_INPUT) return {items: [], invalid: 1, truncated: false, ignoredHeaders: 0};
        var all = text.split("\n"), items = [], invalid = 0, first = true, ignoredHeaders = 0;
        var truncated = text.length > 0 && text.charAt(text.length - 1) !== "\n";
        for (var i = 0; i < all.length; i++) {
            if (!all[i].trim()) continue;
            if (first && allowLogHeader && knownLogHeader(all[i])) { ignoredHeaders++; first = false; continue; }
            first = false;
            if (all[i].length > 131072) { invalid++; continue; }
            try {
                var object = JSON.parse(all[i]);
                if (!object || typeof object !== "object" || Array.isArray(object)) invalid++;
                else items.push({object: object, line: all[i]});
            } catch (ignore) { invalid++; }
        }
        return {items: items, invalid: invalid, truncated: truncated, ignoredHeaders: ignoredHeaders};
    }
    function decimalField(entry, key) {
        var value = entry.object[key];
        if (!finite(value) && typeof value !== "string") return null;
        // Preserve the emitted decimal lexeme instead of rounding it through a JS Date or Number.
        var re = new RegExp('"' + key + '"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)');
        var m = re.exec(entry.line);
        return unixDecimal(m ? m[1] : value);
    }
    function protocol(text) {
        var parsed = lines(text), result = {windows: [], errors: parsed.invalid, truncated: parsed.truncated,
            ready: false, finalSeen: false, finalRestored: false};
        var expected = 0, active = null;
        for (var i = 0; i < parsed.items.length; i++) {
            var entry = parsed.items[i], o = entry.object;
            if (result.finalSeen) { result.errors++; continue; }
            if (o.state === "failsafe-ready") {
                if (result.ready || active || expected !== 0) result.errors++;
                else result.ready = true;
            } else if (o.state === "armed") {
                if (!result.ready || active || !integer(o.trial) || o.trial !== expected || expected >= IDS.length) { result.errors++; continue; }
                var start = decimalField(entry, "source_start");
                if (!start || start.seconds <= 0) { result.errors++; continue; }
                if (result.windows.length && compare(start, result.windows[result.windows.length - 1].end) < 0) { result.errors++; continue; }
                active = {index: expected, start: start};
            } else if (o.state === "window-off") {
                if (!active || !integer(o.trial) || o.trial !== active.index) { result.errors++; continue; }
                var end = decimalField(entry, "source_end"), elapsed = o.elapsed;
                var duration = end ? deltaSeconds(end, active.start) : NaN;
                var valid = !!end && finite(elapsed) && elapsed >= 2.5 && elapsed <= 3.5 && duration >= 2.5 && duration <= 3.5 &&
                    Math.abs(duration - elapsed) <= 0.25 && o.logging_restored === true && o.window_complete === true;
                result.windows.push({index: active.index, start: active.start, end: end || active.start,
                    elapsed: finite(elapsed) ? elapsed : 0, valid: valid, loggingRestored: o.logging_restored === true});
                if (!valid) result.errors++;
                active = null; expected++;
            } else if (o.state === "failsafe-restored") {
                result.finalSeen = true;
                result.finalRestored = !active && result.ready && o.logging_restored === true;
                if (!result.finalRestored) result.errors++;
            } else result.errors++;
        }
        if (active) result.errors++;
        return result;
    }
    function kernelIdentity(o) {
        var supplied = false;
        if (o.process !== undefined) { supplied = true; if (o.process !== "kernel") return {valid: false, supplied: supplied}; }
        if (o.processImagePath !== undefined) {
            supplied = true;
            if (typeof o.processImagePath !== "string" || o.processImagePath.split("/").pop() !== "kernel") return {valid: false, supplied: supplied};
        }
        if (o.processID !== undefined) { supplied = true; if (o.processID !== 0) return {valid: false, supplied: supplied}; }
        if (o.processIdentifier !== undefined) { supplied = true; if (o.processIdentifier !== 0) return {valid: false, supplied: supplied}; }
        return {valid: true, supplied: supplied};
    }
    function normalizeStatus(value) {
        if (!value || value === "ok" || value === "complete" || value === "completed") return {ok: true, reason: "none"};
        if (typeof value !== "string") return {ok: false, reason: "external-status-unrecognized"};
        var status = value.replace(/_/g, "-");
        var allowed = ["control-failed", "positive-control-missing", "session-error", "restoration-unverified", "interrupted", "helper-failed", "logger-failed", "permission-denied", "aborted", "incomplete", "timeout", "restore-failed", "input-read-failed"];
        return {ok: false, reason: allowed.indexOf(status) >= 0 ? status : "external-status-unrecognized"};
    }
    function analyze(rawText, protocolText, prefix, statusReason) {
        var p = protocol(protocolText), raw = lines(rawText, true), counters = {
            invalid_prefix: !prefixOK(prefix), malformed_raw_lines: raw.invalid, raw_truncated: raw.truncated,
            ignored_known_log_headers: raw.ignoredHeaders,
            malformed_protocol_lines_or_states: p.errors, protocol_truncated: p.truncated,
            unknown_prefix_traces: 0, malformed_trace_messages: 0, unattributed_traces: 0,
            non_kernel_traces: 0, duplicate_channel_records: 0, outside_window_records: 0};
        var trials = IDS.map(function (id, index) { return {index: index, id: id, window_complete: false,
            valid: false, logging_restored: false, record_count: 0, record_limit_reached: false,
            timestamp_order_errors: 0, kernel_identity_present_count: 0, records: [], reason: "window-not-complete"}; });
        var previous = [];
        for (var wi = 0; wi < p.windows.length; wi++) {
            var w = p.windows[wi], t = trials[w.index];
            t.window_complete = w.valid; t.logging_restored = w.loggingRestored;
            t.window_elapsed_seconds = w.elapsed;
        }
        for (var i = 0; i < raw.items.length; i++) {
            var o = raw.items[i].object;
            if (o.state !== undefined) { counters.duplicate_channel_records++; continue; }
            if (typeof o.eventMessage !== "string") continue;
            var trace = message(o.eventMessage, prefix);
            if (!trace) {
                if (prefixOK(prefix) && o.eventMessage.indexOf(prefix + ": sending key ") === 0) counters.malformed_trace_messages++;
                else if (/^[A-Za-z0-9_. -]{1,80}: sending key /.test(o.eventMessage)) counters.unknown_prefix_traces++;
                continue;
            }
            var identity = kernelIdentity(o);
            if (!identity.valid) { counters.non_kernel_traces++; continue; }
            var stamp = sourceTimestamp(o.timestamp);
            if (!stamp) { counters.unattributed_traces++; continue; }
            var matched = -1;
            for (wi = 0; wi < p.windows.length; wi++) {
                if (inWindow(stamp, p.windows[wi].start, p.windows[wi].end)) { matched = wi; break; }
            }
            if (matched < 0) { counters.outside_window_records++; continue; }
            w = p.windows[matched]; t = trials[w.index];
            if (previous[w.index] && compare(stamp, previous[w.index]) < 0) t.timestamp_order_errors++;
            previous[w.index] = stamp;
            t.record_count++;
            if (identity.supplied) t.kernel_identity_present_count++;
            if (t.records.length >= MAX_RECORDS) { t.record_limit_reached = true; continue; }
            trace.source_offset_ms = deltaSeconds(stamp, w.start) * 1000;
            t.records.push(trace);
        }
        var sourceValid = !counters.invalid_prefix && !counters.malformed_raw_lines && !counters.raw_truncated &&
            !counters.malformed_protocol_lines_or_states && !counters.protocol_truncated && !counters.unknown_prefix_traces &&
            !counters.malformed_trace_messages && !counters.unattributed_traces && !counters.non_kernel_traces && !counters.duplicate_channel_records;
        for (i = 0; i < trials.length; i++) {
            t = trials[i];
            t.valid = sourceValid && t.window_complete && !t.record_limit_reached && !t.timestamp_order_errors;
            t.reason = !sourceValid ? "trace-or-protocol-source-invalid" : !t.window_complete ? "window-not-complete" :
                t.record_limit_reached ? "record-limit-exceeded" : t.timestamp_order_errors ? "timestamp-order-invalid" :
                t.record_count ? "numeric-driver-trace-captured" : "valid-window-with-no-numeric-driver-trace";
        }
        var controlRecords = trials[0].records.filter(function (r) { return r.adb_code === 0x60; });
        var positive = trials[0].valid && controlRecords.length === 2 && controlRecords[0].down === true &&
            controlRecords[1].down === false && controlRecords[0].mapped_scan === 0x3f && controlRecords[1].mapped_scan === 0x3f &&
            controlRecords[0].raw_scan === controlRecords[1].raw_scan;
        var control = {passed: positive, f5_record_count: controlRecords.length, window_valid: trials[0].valid,
            reason: positive ? "one-f5-down-up-pair-observed" : "f5-positive-control-not-established"};
        function sequence(t) { return t.records.map(function (r) { return [r.raw_scan, r.mapped_scan, r.adb_code, r.down]; }); }
        var comparison = "insufficient-data";
        if (positive && trials[4].valid && trials[5].valid && trials[4].records.length && trials[5].records.length)
            comparison = JSON.stringify(sequence(trials[4])) === JSON.stringify(sequence(trials[5])) ? "identical-driver-trace-sequence" : "different-driver-trace-sequence";
        var external = normalizeStatus(statusReason), allValid = trials.every(function (t) { return t.valid; });
        var complete = positive && allValid && p.windows.length === IDS.length && p.finalSeen && p.finalRestored && external.ok;
        return {schema: 1, parser_version: "1.0.0", result: complete ? "CAPTURED" : "INCONCLUSIVE",
            collection_complete: complete, trace_transport_confirmed: positive, positive_validation: control,
            source_validation: counters, failsafe_final_seen: p.finalSeen,
            logging_restored: p.finalRestored && p.errors === 0 && !p.truncated && external.reason !== "restoration-unverified" && external.reason !== "restore-failed",
            external_status_reason: external.reason, trials: trials,
            comparisons: {direct_f9_versus_ordinary_command_l: comparison},
            limitations: ["Driver trace follows packet parsing, macro inversion and special handling; it is not a raw PS2 wire capture.",
                "Empty target traces do not prove absent physical, PS2 or ACPI firmware events.",
                "No key action or mapping is implemented by this diagnostic."]};
    }
    function check(raw, proto, prefix, index) {
        var report = analyze(raw, proto, prefix);
        index = index === undefined ? 0 : Number(index);
        if (!integer(index) || index < 0 || index >= IDS.length) return {ok: false, reason: "trial-index-invalid"};
        var ok = report.positive_validation.passed && report.trials[index].valid;
        return {ok: ok, trial: index, positive_validation: report.positive_validation,
            trial_valid: report.trials[index].valid, record_count: report.trials[index].record_count,
            source_validation: report.source_validation, reason: ok ? "checkpoint-valid" : "checkpoint-inconclusive"};
    }
    function fixture() {
        var start = 1700000000, frames = [{state: "failsafe-ready"}], rows = [];
        for (var i = 0; i < IDS.length; i++) {
            frames.push({state: "armed", trial: i, source_start: start + i * 10});
            frames.push({state: "window-off", trial: i, source_end: start + i * 10 + 3,
                elapsed: 3, logging_restored: true, window_complete: true});
        }
        frames.push({state: "failsafe-restored", logging_restored: true});
        function row(index, fraction, body) {
            return {timestamp: new Date((start + index * 10) * 1000).toISOString().replace(".000Z", "." + fraction + "Z"),
                processID: 0, processImagePath: "/kernel", eventMessage: "ApplePS2Keyboard: sending key " + body};
        }
        rows.push(row(0, "100000000", "3f=60 down"));
        rows.push(row(0, "200000000", "3f=60 up"));
        [4, 5].forEach(function (index) {
            rows.push(row(index, "100000000", "38=37 down"));
            rows.push(row(index, "200000000", "26=25 down"));
            rows.push(row(index, "300000000", "26=25 up"));
            rows.push(row(index, "400000000", "38=37 up"));
        });
        function ndjson(items) { return items.map(function (item) { return JSON.stringify(item); }).join("\n") + "\n"; }
        return {rows: rows, frames: frames, raw: ndjson(rows), protocol: ndjson(frames), ndjson: ndjson, row: row};
    }
    function selfTest() {
        var checks = [], f = fixture(), prefix = "ApplePS2Keyboard";
        function test(name, passed) { checks.push({name: name, passed: !!passed}); }
        var valid = analyze(f.raw, f.protocol, prefix, "complete");
        test("complete-six-window-session", valid.collection_complete && valid.logging_restored);
        test("positive-control-down-up", valid.positive_validation.passed);
        test("empty-target-is-not-a-failed-positive", valid.trials[1].valid && valid.trials[1].record_count === 0);
        test("f9-command-l-identical-numeric-sequence", valid.comparisons.direct_f9_versus_ordinary_command_l === "identical-driver-trace-sequence");
        test("checkpoint-before-final-message", check(f.ndjson(f.rows.slice(0, 2)), f.ndjson(f.frames.slice(0, 3)), prefix, 0).ok);
        test("plain-trace-grammar", message("ApplePS2Keyboard: sending key 3f=60 down", prefix).adb_code === 96);
        test("remapped-trace-grammar", message("ApplePS2Keyboard: sending key e067=3f, 3f=60 down\n", prefix).raw_scan === 0xe067);
        test("remapped-inconsistent-middle-rejected", message("ApplePS2Keyboard: sending key e067=3f, 40=60 down", prefix) === null);
        test("adb-overflow-rejected", message("ApplePS2Keyboard: sending key 3f=100 down", prefix) === null);
        test("formatter-index-100-retained", message("ApplePS2Keyboard: sending key 100=80 down", prefix) !== null);
        test("suffix-text-rejected", message("ApplePS2Keyboard: sending key 3f=60 down PRIVATE_SENTINEL", prefix) === null);
        test("prefix-regex-escaped", message("PS2Xtest: sending key 3f=60 down", "PS2.test") === null);
        test("microsecond-order-preserved", compare(sourceTimestamp("2026-10-21T12:00:00.123456789Z"), sourceTimestamp("2026-10-21T12:00:00.123456788Z")) > 0);
        test("offset-timezone-equal", compare(sourceTimestamp("2026-10-21 14:00:00.123456+0200"), sourceTimestamp("2026-10-21T12:00:00.123456Z")) === 0);
        test("invalid-calendar-date-rejected", sourceTimestamp("2026-02-30T12:00:00Z") === null);
        var duplicate = [f.rows[0], f.rows[0], f.rows[1]].concat(f.rows.slice(2));
        test("duplicate-f5-down-rejects-control", !analyze(f.ndjson(duplicate), f.protocol, prefix).positive_validation.passed);
        test("missing-f5-up-rejects-control", !analyze(f.ndjson([f.rows[0]]), f.protocol, prefix).positive_validation.passed);
        var outside = JSON.parse(JSON.stringify(f.rows)); outside[0].timestamp = "2023-11-14T22:13:19.999999999Z";
        test("one-nanosecond-before-start-excluded", analyze(f.ndjson(outside), f.protocol, prefix).trials[0].record_count === 1);
        outside[0].timestamp = "2023-11-14T22:13:23.000000000Z";
        test("exact-end-excluded", analyze(f.ndjson(outside), f.protocol, prefix).trials[0].record_count === 1);
        var badTime = JSON.parse(JSON.stringify(f.rows)); delete badTime[0].timestamp;
        test("unattributed-trace-fails-source", analyze(f.ndjson(badTime), f.protocol, prefix).source_validation.unattributed_traces === 1 && !analyze(f.ndjson(badTime), f.protocol, prefix).positive_validation.passed);
        var unknown = JSON.parse(JSON.stringify(f.rows)); unknown[0].eventMessage = "OtherKeyboard: sending key 3f=60 down";
        test("unknown-prefix-fails-source", analyze(f.ndjson(unknown), f.protocol, prefix).source_validation.unknown_prefix_traces === 1);
        var userProcess = JSON.parse(JSON.stringify(f.rows)); userProcess[0].processID = 99;
        test("user-process-echo-rejected", !analyze(f.ndjson(userProcess), f.protocol, prefix).positive_validation.passed);
        test("protocol-echo-in-raw-rejected", analyze(f.raw + f.ndjson([f.frames[0]]), f.protocol, prefix).source_validation.duplicate_channel_records === 1);
        test("truncated-json-channel-rejected", !analyze(f.raw.slice(0, -1), f.protocol, prefix).positive_validation.passed);
        var order = JSON.parse(JSON.stringify(f.frames)); order[1].trial = 1;
        test("trial-order-violation-rejected", !analyze(f.raw, f.ndjson(order), prefix).positive_validation.passed);
        test("missing-final-restore-inconclusive", !analyze(f.raw, f.ndjson(f.frames.slice(0, -1)), prefix).collection_complete);
        var cap = f.rows.slice(0, 2); for (var i = 0; i < 127; i++) cap.push(f.row(1, "100000000", "e063=80 down"));
        cap.push(f.row(1, "200000000", "e063=80 up")); cap.push(f.row(1, "300000000", "e063=80 down"));
        var capped = analyze(f.ndjson(cap), f.protocol, prefix);
        test("record-limit-fails-target-without-overretaining", capped.trials[1].record_limit_reached && !capped.trials[1].valid && capped.trials[1].records.length === 128);
        var privateRows = JSON.parse(JSON.stringify(f.rows)); privateRows[0].unused = "PRIVATE_SENTINEL";
        var privateReport = JSON.stringify(analyze(f.ndjson(privateRows), f.protocol, prefix, "PRIVATE_SENTINEL"));
        test("raw-and-status-text-never-echoed", privateReport.indexOf("PRIVATE_SENTINEL") < 0 && privateReport.indexOf("eventMessage") < 0 && privateReport.indexOf("/kernel") < 0);
        test("partial-startup-report-inconclusive", !analyze("", "", prefix, "session_error").collection_complete && !analyze("", "", prefix).logging_restored);
        return {result: checks.every(function (item) { return item.passed; }) ? "SELF_TEST_PASSED" : "SELF_TEST_FAILED", checks: checks};
    }
    return {analyze: analyze, check: check, message: message, sourceTimestamp: sourceTimestamp,
        unixDecimal: unixDecimal, compare: compare, protocol: protocol, maximumInput: MAX_INPUT,
        selfTest: selfTest, fixture: fixture};
}());

if (typeof module !== "undefined" && module.exports) module.exports = S540Trace;

function run(argv) {
    "use strict";
    if (Array.isArray(argv) && argv.length === 1 && argv[0] === "self-test") {
        var tested = S540Trace.selfTest();
        if (tested.result !== "SELF_TEST_PASSED") throw new Error("S540_TRACE_SELF_TEST_FAILED");
        return JSON.stringify(tested);
    }
    ObjC.import("Foundation");
    function readText(path) {
        if (typeof path !== "string" || path.charAt(0) !== "/") throw new Error("S540_TRACE_INPUT_PATH_INVALID");
        var attrs = $.NSFileManager.defaultManager.attributesOfItemAtPathError($(path), null);
        if (!attrs || Number(ObjC.unwrap(attrs.objectForKey($.NSFileSize))) > S540Trace.maximumInput) throw new Error("S540_TRACE_INPUT_UNAVAILABLE");
        var value = $.NSString.stringWithContentsOfFileEncodingError($(path), $.NSUTF8StringEncoding, null);
        var text = value ? ObjC.unwrap(value) : undefined;
        if (typeof text !== "string") throw new Error("S540_TRACE_INPUT_UNAVAILABLE");
        return text;
    }
    if (!Array.isArray(argv) || (argv[0] !== "check" && argv[0] !== "report") || argv.length < 4)
        throw new Error("S540_TRACE_USAGE_INVALID");
    var raw = readText(argv[1]), proto = readText(argv[2]), prefix = argv[3];
    if (argv[0] === "check") {
        if (argv.length > 5) throw new Error("S540_TRACE_USAGE_INVALID");
        var checked = S540Trace.check(raw, proto, prefix, argv.length === 5 ? argv[4] : 0);
        if (!checked.ok) throw new Error("S540_TRACE_CHECKPOINT_INCONCLUSIVE");
        return JSON.stringify(checked);
    }
    if (argv.length < 5 || argv.length > 6 || typeof argv[4] !== "string" || argv[4].charAt(0) !== "/")
        throw new Error("S540_TRACE_OUTPUT_PATH_INVALID");
    var report = S540Trace.analyze(raw, proto, prefix, argv[5]);
    var data = $(JSON.stringify(report, null, 2)).dataUsingEncoding($.NSUTF8StringEncoding);
    if (!data.writeToFileOptionsError($(argv[4]), $.NSDataWritingWithoutOverwriting, null))
        throw new Error("S540_TRACE_REPORT_WRITE_FAILED");
    return JSON.stringify({result: report.result, collection_complete: report.collection_complete,
        trace_transport_confirmed: report.trace_transport_confirmed, logging_restored: report.logging_restored});
}
