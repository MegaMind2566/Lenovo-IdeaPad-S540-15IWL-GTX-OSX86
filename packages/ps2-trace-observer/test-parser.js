"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const parser = require("./parse-trace.js");

const tested = parser.selfTest();
assert.equal(tested.result, "SELF_TEST_PASSED");
assert(tested.checks.length >= 29);
const f = parser.fixture();
const prefix = "ApplePS2Keyboard";
let extra = 0;
function test(name, work) { work(); extra++; }

test("literal protocol ready state", () => {
  const frames = JSON.parse(JSON.stringify(f.frames));
  frames[0].state = "ready";
  assert(!parser.analyze(f.raw, f.ndjson(frames), prefix).positive_validation.passed);
});
test("exact leading log predicate header permitted once", () => {
  for (const field of ["eventMessage", "composedMessage"]) {
    const header = `Filtering the log data using "${field} CONTAINS "sending key""\n`;
    const report = parser.analyze(header + f.raw, f.protocol, prefix);
    assert(report.collection_complete);
    assert.equal(report.source_validation.ignored_known_log_headers, 1);
    assert(!JSON.stringify(report).includes("Filtering the log"));
  }
});
test("known header with outer single quotes", () => {
  const header = `Filtering the log data using 'eventMessage CONTAINS "sending key"'\n`;
  assert(parser.analyze(header + f.raw, f.protocol, prefix).positive_validation.passed);
});
test("midstream or repeated header is rejected", () => {
  const header = 'Filtering the log data using "eventMessage CONTAINS "sending key""\n';
  assert(!parser.analyze(f.raw + header, f.protocol, prefix).positive_validation.passed);
  assert(!parser.analyze(header + header + f.raw, f.protocol, prefix).positive_validation.passed);
});
test("different predicate header is rejected", () => {
  const header = 'Filtering the log data using "eventMessage CONTAINS "PRIVATE_SENTINEL""\n';
  const report = parser.analyze(header + f.raw, f.protocol, prefix);
  assert(!report.positive_validation.passed);
  assert(!JSON.stringify(report).includes("PRIVATE_SENTINEL"));
});
test("raw break-bit domain differs from custom mapped byte domain", () => {
  assert.equal(parser.message("ApplePS2Keyboard: sending key 80=60 down", prefix), null);
  assert.equal(parser.message("ApplePS2Keyboard: sending key e080=60 down", prefix), null);
  assert(parser.message("ApplePS2Keyboard: sending key 3f=80, 80=60 down", prefix));
});
test("duplicate ready", () => {
  assert(!parser.analyze(f.raw, f.ndjson([f.frames[0]].concat(f.frames)), prefix).positive_validation.passed);
});
test("duplicate off", () => {
  const frames = f.frames.slice(); frames.splice(3, 0, frames[2]);
  assert(!parser.analyze(f.raw, f.ndjson(frames), prefix).collection_complete);
});
test("source clock divergence", () => {
  const frames = JSON.parse(JSON.stringify(f.frames)); frames[2].source_end += 0.4;
  assert(!parser.analyze(f.raw, f.ndjson(frames), prefix).positive_validation.passed);
});
test("not restored field is false", () => {
  const frames = JSON.parse(JSON.stringify(f.frames)); frames[2].logging_restored = false;
  assert(!parser.analyze(f.raw, f.ndjson(frames), prefix).positive_validation.passed);
});
test("restoration unverified external status", () => {
  const report = parser.analyze(f.raw, f.protocol, prefix, "restoration_unverified");
  assert(!report.logging_restored); assert(!report.collection_complete);
});
test("complete status supported", () => {
  assert(parser.analyze(f.raw, f.protocol, prefix, "complete").collection_complete);
});
test("zero records positive fails but empty targets retained", () => {
  const report = parser.analyze("", f.protocol, prefix);
  assert(!report.positive_validation.passed);
  assert(report.trials[1].valid && report.trials[1].record_count === 0);
});
test("bad timestamp granularity not rounded into window", () => {
  const rows = JSON.parse(JSON.stringify(f.rows));
  rows[0].timestamp = "2023-11-14T22:13:19.999999999Z";
  assert(!parser.analyze(f.ndjson(rows), f.protocol, prefix).positive_validation.passed);
});
test("both F9 and ordinary CmdL required for comparison", () => {
  const rows = f.rows.filter(row => !row.timestamp.startsWith("2023-11-14T22:14:10"));
  assert.equal(parser.analyze(f.ndjson(rows), f.protocol, prefix).comparisons.direct_f9_versus_ordinary_command_l, "insufficient-data");
});
test("numeric difference distinguished without remapping", () => {
  const rows = JSON.parse(JSON.stringify(f.rows));
  rows[2].eventMessage = "ApplePS2Keyboard: sending key e05b=37 down";
  assert.equal(parser.analyze(f.ndjson(rows), f.protocol, prefix).comparisons.direct_f9_versus_ordinary_command_l, "different-driver-trace-sequence");
});
test("protocol absent gives partial inconclusive report", () => {
  const report = parser.analyze("", "", prefix, "session_error");
  assert.equal(report.result, "INCONCLUSIVE"); assert.equal(report.logging_restored, false);
  assert.equal(report.external_status_reason, "session-error");
});
test("unknown prefix input is not echoed", () => {
  const report = parser.analyze(f.raw, f.protocol, "INJECT\nPRIVATE_SENTINEL");
  assert(report.source_validation.invalid_prefix);
  assert(!JSON.stringify(report).includes("PRIVATE_SENTINEL"));
});
test("arbitrary raw text is not echoed", () => {
  const report = parser.analyze("PRIVATE_SENTINEL\n", f.protocol, prefix);
  assert(report.source_validation.malformed_raw_lines);
  assert(!JSON.stringify(report).includes("PRIVATE_SENTINEL"));
});
test("timestamp exponent decimal preserves source lexeme", () => {
  assert.deepEqual(parser.unixDecimal("1.700000000123456789e9"), {seconds:1700000000,nanos:123456789});
  assert.equal(parser.unixDecimal("1700000000.1234567891"), null);
});
test("kernel metadata optional but conflict fails", () => {
  const rows = JSON.parse(JSON.stringify(f.rows));
  rows.forEach(row => { delete row.processID; delete row.processImagePath; });
  assert(parser.analyze(f.ndjson(rows), f.protocol, prefix).positive_validation.passed);
  rows[0].process = "Finder";
  assert(!parser.analyze(f.ndjson(rows), f.protocol, prefix).positive_validation.passed);
});
test("reversed time order invalidates a window", () => {
  const rows = [f.rows[1], f.rows[0]].concat(f.rows.slice(2));
  assert(parser.analyze(f.ndjson(rows), f.protocol, prefix).trials[0].timestamp_order_errors > 0);
});

// Exercise JXA glue with Foundation-shaped stubs. This is not native macOS execution.
const files = {"/raw.ndjson": f.raw, "/protocol.ndjson": f.protocol};
const imports = [];
function unbox(v) { return v && typeof v === "object" && Object.hasOwn(v, "value") ? v.value : v; }
function wrap(v) {
  return {value:v, dataUsingEncoding() {
    return {writeToFileOptionsError(output, options) {
      output = unbox(output);
      assert.equal(options, 2);
      if (Object.hasOwn(files, output)) return false;
      files[output] = v; return true;
    }};
  }};
}
wrap.NSFileSize = "NSFileSize"; wrap.NSUTF8StringEncoding = 4; wrap.NSDataWritingWithoutOverwriting = 2;
wrap.NSFileManager = {defaultManager: {attributesOfItemAtPathError(file) {
  file = unbox(file);
  return Object.hasOwn(files, file) ? {objectForKey() { return wrap(Buffer.byteLength(files[file])); }} : null;
}}};
wrap.NSString = {stringWithContentsOfFileEncodingError(file) {
  file = unbox(file); return Object.hasOwn(files, file) ? wrap(files[file]) : null;
}};
const context = vm.createContext({$:wrap, ObjC:{import(name) { imports.push(name); }, unwrap:unbox}});
vm.runInContext(fs.readFileSync(path.join(__dirname, "parse-trace.js"), "utf8"), context);
test("CLI self-test does not touch Foundation", () => {
  assert.equal(JSON.parse(context.run(["self-test"])).result, "SELF_TEST_PASSED");
  assert.equal(imports.length, 0);
});
test("CLI check bridge succeeds", () => {
  assert(JSON.parse(context.run(["check", "/raw.ndjson", "/protocol.ndjson", prefix, "0"])).ok);
});
test("CLI check fails with constant error", () => {
  files["/empty.ndjson"] = "";
  assert.throws(() => context.run(["check", "/empty.ndjson", "/protocol.ndjson", prefix, "0"]), /S540_TRACE_CHECKPOINT_INCONCLUSIVE/);
});
test("CLI report bridge writes numeric report", () => {
  const result = JSON.parse(context.run(["report", "/raw.ndjson", "/protocol.ndjson", prefix, "/report.json", "complete"]));
  assert.equal(result.result, "CAPTURED");
  const report = JSON.parse(files["/report.json"]);
  assert(report.collection_complete);
  assert(!files["/report.json"].includes("eventMessage"));
});
test("CLI does not overwrite output", () => {
  assert.throws(() => context.run(["report", "/raw.ndjson", "/protocol.ndjson", prefix, "/report.json"]), /S540_TRACE_REPORT_WRITE_FAILED/);
});
test("CLI missing input gives constant error", () => {
  assert.throws(() => context.run(["check", "/missing", "/protocol.ndjson", prefix, "0"]), /S540_TRACE_INPUT_UNAVAILABLE/);
});
test("CLI partial report still written", () => {
  const result = JSON.parse(context.run(["report", "/empty.ndjson", "/empty.ndjson", prefix, "/partial.json", "session_error"]));
  assert.equal(result.result, "INCONCLUSIVE");
  assert.equal(JSON.parse(files["/partial.json"]).logging_restored, false);
});

console.log(JSON.stringify({result:"PASSED", core_checks:tested.checks.length, additional_node_checks:extra,
  native_jxa_verified:false}));
