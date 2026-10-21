#!/usr/bin/env python3
"""Exercise the production Bash flow in an isolated Linux PTY with fake macOS dependencies.

This checks shell protocol/cleanup only. It does not execute Mach-O, JXA, IOKit or macOS log.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import tempfile
import termios
import time

SOURCE = Path(__file__).resolve().parents[1] / 'CONTROLLA-TASTI.command'

FAKE = r'''#!/usr/bin/env python3
import json,os,pathlib,select,signal,sys,time
name=pathlib.Path(sys.argv[0]).name
root=pathlib.Path(os.environ['FIXTURE_STATE'])
scenario=os.environ['FIXTURE_SCENARIO']
args=sys.argv[1:]
def write_state(value): (root/'state').write_text(str(value))
def emit(value): print(json.dumps(value,separators=(',',':')),flush=True)
if name=='uname':
 print('Darwin' if '-s' in args else 'x86_64');sys.exit()
if name=='id': print('501');sys.exit()
if name=='codesign':sys.exit()
if name=='sleep':time.sleep(max(.03,min(.10,float(args[0])*.08)));sys.exit()
if name=='sudo':
 if args==['-v']:sys.exit()
 if args and args[0]=='-n':args=args[1:]
 if args and args[0]=='--':args=args[1:]
 os.execv(args[0],args)
if name=='plutil':
 try:
  value=json.loads(sys.stdin.read())[args[args.index('-extract')+1]]
  print(str(value).lower() if isinstance(value,bool) else value)
 except Exception:sys.exit(1)
 sys.exit()
if name=='ioreg':
 print('+-o ApplePS2Keyboard  <class ApplePS2Keyboard, id 0x100000378>')
 print('    "LogScanCodes" = '+(root/'state').read_text().strip());sys.exit()
if name=='log':
 if scenario=='logger-startup-error':
  print('FIXTURE log: unsupported output style',file=sys.stderr,flush=True);sys.exit(2)
 while True:
  time.sleep(.01)
if name=='osascript':
 mode=args[3]
 if mode=='self-test':print('FIXTURE parser self-test');sys.exit()
 if mode=='check':
  if scenario=='parser-error':
   print('FIXTURE parser: bad schema',file=sys.stderr);sys.exit(3)
  sys.exit(1 if scenario=='positive-missing' else 0)
 if mode=='report':
  pathlib.Path(args[7]).write_text(json.dumps({'fixture':True,'reason':args[8]}));sys.exit()
 sys.exit(64)
if name=='function-key-scancodes':
 if args==['--self-test']:
  print('Pure scan-code, loaded-identity and privacy fixture checks passed: 64');sys.exit()
 if args!=['--failsafe']:sys.exit(64)
 stopped=False
 def stop(*unused):
  global stopped
  stopped=True
 for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,stop)
 # Descriptor inheritance would keep EOF from reaching this reader.
 emit({'state':'failsafe-ready','registry_id':4294968184})
 index=0
 try:
  while index<10 and not stopped:
   line=sys.stdin.readline()
   if line!=f'ARM {index}\n':break
   with (root/'arms').open('a') as f:f.write(str(index)+'\n')
   write_state(2)
   started=time.time();deadline=time.monotonic()+.30
   emit({'state':'armed','trial':index,'source_start':started,'deadline':deadline})
   cancelled=False
   while not stopped and time.monotonic()<deadline:
    if select.select([sys.stdin],[],[],.01)[0]:cancelled=True;break
   complete=not cancelled and not stopped
   off_ok=scenario!='off-restoration-false'
   write_state(0 if off_ok else 2)
   emit({'state':'window-off','trial':index,'logging_restored':off_ok,
         'window_complete':complete,'source_end':time.time(),'elapsed':time.time()-started})
   if not complete:break
   index+=1
 finally:
  write_state(0)
  emit({'state':'failsafe-restored','logging_restored':True})
 sys.exit()
raise SystemExit('Unknown fake command '+name)
'''

BASH_FAKE = r'''#!/bin/bash
case "${0##*/}" in
 uname) if [ "$1" = -s ]; then echo Darwin; else echo x86_64; fi ;;
 id) echo 501 ;;
 codesign) exit 0 ;;
 sleep) /bin/sleep .05 ;;
 stty)
   if [ "$FIXTURE_SCENARIO" = tty-prepare-error ] && [ "$1" = -echo ]; then
     echo 'FIXTURE stty: prepare failure' >&2; exit 1
   fi
   exec /bin/stty "$@" ;;
 sudo)
   [ "$1" != -v ] || exit 0
   [ "$1" != -n ] || shift
   [ "$1" != -- ] || shift
   exec "$@" ;;
 plutil)
   KEY=$2
   IFS= read -r LINE
   VALUE=${LINE#*\"$KEY\":}
   [ "$VALUE" != "$LINE" ] || exit 1
   if [ "${VALUE:0:1}" = '"' ]; then VALUE=${VALUE:1}; VALUE=${VALUE%%\"*};
   else VALUE=${VALUE%%,*}; VALUE=${VALUE%%\}*}; fi
   printf '%s\n' "$VALUE" ;;
 ioreg)
   printf '%s\n' '+-o ApplePS2Keyboard  <class ApplePS2Keyboard, id 0x100000378>'
   if [ "$FIXTURE_SCENARIO" = final-readback-mismatch ] && [ -s "$FIXTURE_STATE/arms" ]; then VALUE=2;
   else VALUE=$(cat "$FIXTURE_STATE/state"); fi
   printf '    "LogScanCodes" = %s\n' "$VALUE" ;;
 *) exit 65 ;;
esac
'''


def run_case(scenario: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='s540-shell-fixture-') as directory:
        base = Path(directory)
        package = base/'package'
        fake = base/'fake'
        state = base/'state'
        home = base/'home'
        for path in (package/'bin', fake, state, home/'Desktop'):
            path.mkdir(parents=True)
        (state/'state').write_text('0')
        (state/'arms').write_text('')
        driver = fake/'driver.py'
        driver.write_text(FAKE)
        driver.chmod(0o755)
        mappings = {
            '/usr/bin/uname': 'uname', '/usr/bin/id': 'id',
            '/usr/bin/codesign': 'codesign', '/usr/bin/sudo': 'sudo',
            '/usr/bin/osascript': 'osascript', '/usr/bin/plutil': 'plutil',
            '/usr/sbin/ioreg': 'ioreg', '/usr/bin/log': 'log',
            '/bin/sleep': 'sleep',
            '/bin/stty': 'stty',
        }
        script = SOURCE.read_text()
        # All replaced paths are external dependencies; production control flow is unchanged.
        for original, executable in mappings.items():
            target = fake/executable
            if executable in ('uname','id','codesign','sleep','sudo','plutil','ioreg','stty'):
                target.write_text(BASH_FAKE)
                target.chmod(0o755)
            else:
                target.symlink_to(driver)
            script = script.replace(original, str(target))
        # Linux stty has no delayed-suspend character; macOS production keeps it disabled.
        script = script.replace(' dsusp undef', '')
        helper = package/'bin/function-key-scancodes'
        helper.write_text(FAKE)
        helper.chmod(0o755)
        command = package/'CONTROLLA-TASTI.command'
        command.write_text(script)
        (package/'parse-trace.js').write_text('// Fixture parser transport only.\n')
        files = [command, helper, package/'parse-trace.js']
        (package/'SHA256SUMS').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(package))+'\n'
            for p in files))
        env = dict(os.environ, HOME=str(home), TMPDIR=str(base),
                   FIXTURE_STATE=str(state), FIXTURE_SCENARIO=scenario)
        pid, master = pty.fork()
        if pid == 0:
            os.execve('/bin/bash', ['/bin/bash', str(command)], env)
        initial = termios.tcgetattr(master)
        transcript = b''
        sent_enter = False
        sent_interrupt = False
        via_count = 0
        deadline = time.monotonic()+60
        status = None
        while time.monotonic()<deadline:
            ready, _, _ = select.select([master], [], [], .05)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    data = b''
                if data:
                    transcript += data
                    if b'Premi Invio UNA volta' in transcript and not sent_enter:
                        os.write(master, b'\n')
                        sent_enter = True
                    found = transcript.count(b'VIA: adesso.')
                    if found>via_count:
                        via_count=found
                        if scenario=='interrupt-during-window' and not sent_interrupt:
                            os.write(master,b'\x03')
                            sent_interrupt=True
                        else:
                            # Actual terminal contamination from the reported Fn+F5 run.
                            os.write(master,b'\x1b[15~')
            done, result = os.waitpid(pid, os.WNOHANG)
            if done:
                status = os.waitstatus_to_exitcode(result)
                break
        if status is None:
            os.killpg(pid,signal.SIGKILL)
            os.waitpid(pid,0)
            raise AssertionError(scenario+': shell timeout\n'+transcript.decode(errors='replace'))
        restored = termios.tcgetattr(master)==initial
        os.close(master)
        arms = [int(x) for x in (state/'arms').read_text().splitlines()]
        reports=list((home/'Desktop').glob('*/report.json'))
        expected_arms = list(range(6)) if scenario in ('complete','final-readback-mismatch') else ([] if scenario in ('logger-startup-error','tty-prepare-error') else [0])
        expected_exit=0 if scenario in ('complete','positive-missing','parser-error') else (130 if scenario=='interrupt-during-window' else 1)
        assert arms==expected_arms,(scenario,'ARM sequence',arms,transcript.decode(errors='replace'))
        assert status==expected_exit,(scenario,'exit',status,transcript.decode(errors='replace'))
        assert (state/'state').read_text()=='0',(scenario,'logging left enabled')
        assert restored,(scenario,'TTY attributes not restored')
        if scenario=='complete':
            assert reports and json.loads(reports[0].read_text())['reason']=='complete'
        if scenario in ('positive-missing','parser-error'):
            assert reports and json.loads(reports[0].read_text())['reason']=='positive_control_missing'
        diagnostics='\n'.join(p.read_text() for p in (home/'Desktop').glob('*/diagnostics.txt'))
        if scenario=='logger-startup-error':
            assert 'FIXTURE log: unsupported output style' in diagnostics
        if scenario=='parser-error':
            assert 'FIXTURE parser: bad schema' in diagnostics
        if scenario=='final-readback-mismatch':
            assert reports and json.loads(reports[0].read_text())['reason']=='restoration_unverified'
            assert b'Logging ripristinato a 0.\r\n' not in transcript
        return {'scenario':scenario,'passed':True,'exitCode':status,'armedTrials':arms,
                'ttyRestored':restored,'fixtureLoggingState':0,
                'reports':len(reports),
                'startupErrorPreserved':'FIXTURE log: unsupported output style' in diagnostics,
                'parserErrorPreserved':'FIXTURE parser: bad schema' in diagnostics}


if __name__=='__main__':
    scenarios=('complete','positive-missing','logger-startup-error',
               'off-restoration-false','interrupt-during-window','parser-error',
               'tty-prepare-error','final-readback-mismatch')
    results=[]
    for scenario in scenarios:
        result=run_case(scenario)
        results.append(result)
        print(json.dumps(result),flush=True)
    print(json.dumps({'result':'PASSED','cases':len(results),
                      'scope':'Linux PTY + fake macOS dependencies; no Mach-O/JXA/IOKit/macOS execution'}))
