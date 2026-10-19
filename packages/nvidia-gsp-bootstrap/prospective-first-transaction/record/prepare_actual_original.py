#!/usr/bin/env python3
"""Extract complete pinned bodies into an explicit output directory only."""
from pathlib import Path
import argparse,hashlib,json,re
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
OSAPI='src/nvidia/arch/nvalloc/unix/src/osapi.c'
OS='src/nvidia/arch/nvalloc/unix/src/os.c'
TIMER='src/nvidia/src/kernel/gpu/timer/timer.c'
OSTIMER='src/nvidia/src/kernel/gpu/timer/timer_ostimer.c'
SEMA='src/nvidia/src/kernel/gpu/timed_semaphore.c'
FUNCTIONS=[(SEMA,'_class9074TimerCallback'),(TIMER,'tmrIsOSTimer'),(TIMER,'tmrEventOnList_IMPL'),
 (TIMER,'_tmrScanCallbackOSTimer'),(OSTIMER,'tmrEventServiceOSTimerCallback_OSTIMER'),
 (TIMER,'tmrEventServiceTimer_IMPL'),(OS,'osQueueWorkItem'),(OSAPI,'_tmrEventServiceTimerWorkItem'),
 (OSAPI,'RmRunNanoTimerCallback'),(OSAPI,'rm_run_nano_timer_callback'),
 (OSAPI,'RmExecuteWorkItem'),(OSAPI,'rm_execute_work_item')]
SOURCES={SEMA:'39729273dfe4e6396f06527433c46c760acab603753bdee36336eb724e6efe55',
 TIMER:'6bd867db774d01b96976968598f5cfad01e343e745d8b08fe84e1f6a9c4b5c18',
 OSTIMER:'9710b89d0725d433b993ba803983bde1262096e7f62b81d39d0bc8f816ff5bb3',
 OS:'057b50fcb738be90a073b60f63e70559706864ddcec3bf703282563173e3dce4',
 OSAPI:'e4336f0e3bb55122680e0d344f970c123664122c2415134b7a6b517c98fcbe75'}
def body(src,name):
 pattern=r'(?m)^(?:static\s+)?(?:(?:NV_INLINE|inline)\s+)?(?:NV_STATUS|NvBool|NvU32|void)\s+(?:NV_API_CALL\s+)?'+re.escape(name)+r'\s*\('
 matches=[m for m in re.finditer(pattern,src) if ';' not in src[m.end():src.index('{',m.end())]]
 if len(matches)!=1:raise ValueError((name,len(matches)))
 m=matches[0];brace=src.index('{',m.end());depth=0
 for t in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]',src[brace:],re.S):
  if t.group()=='{':depth+=1
  elif t.group()=='}':
   depth-=1
   if depth==0:return src[m.start():brace+t.end()]+'\n'
 raise ValueError(name)
def prepare(upstream,output,original_probes=None):
 upstream=Path(upstream).resolve(strict=True);output=Path(output).resolve()
 if output==HERE or HERE in output.parents:raise ValueError('Generated outputs must be outside the packaged record directory')
 if output==upstream or upstream in output.parents:raise ValueError('Generated outputs must not modify pinned upstream')
 output.mkdir(parents=True,exist_ok=True);bodies=[]
 for rel,expected in SOURCES.items():
  if hashlib.sha256((upstream/rel).read_bytes()).hexdigest()!=expected:raise ValueError('Pinned upstream hash mismatch: '+rel)
 for rel,name in FUNCTIONS:
  bodies.append('\n#line 1 "'+rel+':'+name+'"\n'+body((upstream/rel).read_text(),name))
 (output/'actual-original-bodies.inc').write_text('\n'.join(bodies))
 probes=Path(original_probes or HERE.parent/'original/S540NvidiaGspFirstTransactionOriginal.c').resolve(strict=True)
 src=probes.read_text();meta=['s540FirstTxnInspectOriginalWork','s540FirstTxnInspectOriginalEvent','s540FirstTxnInspectOriginalOwner']
 (output/'actual-original-metadata.inc').write_text('\n'.join(body(src,name) for name in meta))
 result={'format':1,'actual_original_bodies':len(FUNCTIONS),'original_functions':FUNCTIONS,'source_sha256':SOURCES,
  'metadata_reader_sha256':hashlib.sha256(src.encode()).hexdigest(),
  'policy':'TEST-ONLY typed TimedSemaSwObject empty-list control rows. Packaged original policy remains nano WORK-only.',
  'full_nv_h_abi':True,'hardware_admission':False}
 (output/'actual-original-source.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upstream',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();print(json.dumps(prepare(a.upstream,a.output)))
