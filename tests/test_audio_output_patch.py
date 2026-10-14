#!/usr/bin/env python3
"""Execute the patched C++ output and preserved microphone policy on the S540 graph."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

import test_audio_microphone_patch as microphone


STUBS = microphone.STUBS.replace(
    'struct { UInt32 quirks=0; struct { bool digital=false; } assocs[2]; } audio;',
    'struct { UInt32 quirks=0; int numAssocs=2; struct { bool digital=false; } assocs[2]; } audio;',
).replace(
    'int playChanId=1, recChanId=0;', 'int playChanId=1, recChanId=0, digital=0;',
).replace(
    'bool mEnableS540InputGainFix=true, mEnableVolumeChangeFix=true;',
    'bool mEnableS540InputGainFix=true, mEnableVolumeChangeFix=true;\n    bool mEnableS540OutputRangeFix=false;',
).replace(
    'bool s540InputGainFixEnabled(PcmDevice*);',
    'bool s540InputGainFixEnabled(PcmDevice*);\n    bool s540OutputRangeFixEnabled(PcmDevice*);',
).replace(
    'bool mEnableS540InputGainFix=true, mEnableVolumeChangeFix=true, mEnableMuteFix=false;',
    'bool mEnableS540InputGainFix=true, mEnableVolumeChangeFix=true, mEnableMuteFix=false;\n    bool mEnableS540OutputRangeFix=false;',
)

OUTPUT_TESTS = r'''
int main() {
    input_regression();
    Codec codec; FunctionGroup fg; fg.codec=&codec;
    Widget adcWidget, internalWidget, jackWidget, selectorWidget, dacWidget, speakerWidget;
    adcWidget.nid=8; internalWidget.nid=18; jackWidget.nid=25; selectorWidget.nid=35;
    dacWidget.nid=2; dacWidget.bindAssoc=1; speakerWidget.nid=20; speakerWidget.bindAssoc=1;
    AudioControl adc, internal, jack, selector, jackSelector, dac, speaker;
    adc.widget=&adcWidget; adc.mute=1; adc.step=63; adc.size=2; adc.offset=23;
    adc.ossmask=SOUND_MASK_IMIX|SOUND_MASK_RECLEV;
    internal.widget=&internalWidget; internal.step=3; internal.size=39;
    internal.ossmask=SOUND_MASK_MONITOR;
    jack.widget=&jackWidget; jack.step=3; jack.size=39; jack.ossmask=SOUND_MASK_LINE;
    selector.widget=&selectorWidget; selector.mute=1;
    selector.ossmask=SOUND_MASK_RECLEV|SOUND_MASK_MONITOR;
    jackSelector=selector; jackSelector.index=1;
    jackSelector.ossmask=SOUND_MASK_RECLEV|SOUND_MASK_LINE;
    dac.widget=&dacWidget; dac.dir=HDA_CTL_OUT; dac.step=87; dac.size=2; dac.offset=87;
    dac.ossmask=SOUND_MASK_PCM; dac.mute=0;
    speaker.widget=&speakerWidget; speaker.dir=HDA_CTL_OUT; speaker.mute=1;
    speaker.ossmask=SOUND_MASK_VOLUME|SOUND_MASK_PCM;
    fg.controls={&adc,&internal,&jack,&selector,&jackSelector,&dac,&speaker};
    PcmDevice pcm; pcm.funcGroup=&fg;
    VoodooHDADevice device; device.mEnableS540OutputRangeFix=true;
    device.mChannels[0]={&pcm,&fg,0}; device.mChannels[1]={&pcm,&fg,1};
    for(int n=0;n<25;n++) device.mMixerDefaults[n]=95;
    assert(device.s540OutputRangeFixEnabled(&pcm));
    // Every capability/routing mismatch fails closed into the existing policy.
    device.mEnableS540OutputRangeFix=false; assert(!device.s540OutputRangeFixEnabled(&pcm));
    device.mEnableS540OutputRangeFix=true;
    device.mEnableVolumeChangeFix=false; assert(!device.s540OutputRangeFixEnabled(&pcm));
    device.mEnableVolumeChangeFix=true;
    device.mEnableS540InputGainFix=false; assert(!device.s540OutputRangeFixEnabled(&pcm));
    device.mEnableS540InputGainFix=true;
    device.mDeviceId=0x12348086; assert(!device.s540OutputRangeFixEnabled(&pcm)); device.mDeviceId=0x9dc88086;
    codec.deviceId=0x0256; assert(!device.s540OutputRangeFixEnabled(&pcm)); codec.deviceId=0x0257;
    internal.size=38; assert(!device.s540OutputRangeFixEnabled(&pcm)); internal.size=39;
    pcm.digital=1; assert(!device.s540OutputRangeFixEnabled(&pcm)); pcm.digital=0;
    pcm.playChanId=-1; assert(!device.s540OutputRangeFixEnabled(&pcm)); pcm.playChanId=2;
    assert(!device.s540OutputRangeFixEnabled(&pcm)); pcm.playChanId=1;
    device.mChannels[1].assocNum=-1; assert(!device.s540OutputRangeFixEnabled(&pcm));
    device.mChannels[1].assocNum=2; assert(!device.s540OutputRangeFixEnabled(&pcm));
    device.mChannels[1].assocNum=1;
    fg.audio.assocs[1].digital=true; assert(!device.s540OutputRangeFixEnabled(&pcm)); fg.audio.assocs[1].digital=false;
    dacWidget.nid=3; assert(!device.s540OutputRangeFixEnabled(&pcm)); dacWidget.nid=2;
    dacWidget.bindAssoc=-2; assert(!device.s540OutputRangeFixEnabled(&pcm)); dacWidget.bindAssoc=1;
    dac.dir=HDA_CTL_IN; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.dir=HDA_CTL_OUT;
    dac.index=1; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.index=0;
    dac.ossmask=SOUND_MASK_PCM|SOUND_MASK_VOLUME; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.ossmask=SOUND_MASK_PCM;
    dac.step=86; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.step=87;
    dac.size=1; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.size=2;
    dac.offset=86; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.offset=87;
    dac.mute=1; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.mute=0;
    dac.enable=0; assert(!device.s540OutputRangeFixEnabled(&pcm)); dac.enable=1;
    AudioControl unexpected=dac; Widget extra=dacWidget; extra.nid=3; unexpected.widget=&extra;
    fg.controls.push_back(&unexpected); assert(!device.s540OutputRangeFixEnabled(&pcm)); fg.controls.pop_back();
    assert(device.s540OutputRangeFixEnabled(&pcm));
    device.mixerSetDefaults(&pcm);
    assert(adc.left==32 && internal.left==0 && jack.left==0);
    VoodooHDAEngine output; output.mDevice=&device; output.mChannel=&device.mChannels[1];
    output.direction=kIOAudioStreamDirectionOutput; output.mEnableS540OutputRangeFix=true;
    output.oldOutVolumeLeft=output.oldOutVolumeRight=pcm.left[SOUND_MIXER_PCM];
    VoodooHDAEngine input; input.mDevice=&device; input.mChannel=&device.mChannels[0];
    IOAudioControl left, right; right.channel=2;
    UInt64 range=output.getMinMaxDb(SOUND_MASK_PCM);
    assert(int32_t(range>>32)==-4276224 && int32_t(range)==0); // -65.25 / 0 dB
    UInt64 inputRange=input.getMinMaxDb(SOUND_MASK_RECLEV);
    assert(int32_t(inputRange>>32)==-1130496 && int32_t(inputRange)==1966080);
    const int adcGain=adc.left;
    std::set<int> steps; int previous=-1;
    for(int value=0;value<=100;value++) {
        output.volumeChanged(&left,0,value); output.volumeChanged(&right,0,value);
        const int raw=(value*87+50)/100;
        assert(dac.left==raw && dac.right==raw && raw>=previous); previous=raw; steps.insert(raw);
        // The unchanged Main=95 routing factor rounds PCM=1 to pin mute.
        assert(speaker.muted==(value > 1 ? 0U : 3U));
        assert(adc.left==adcGain && internal.left==0 && jack.left==0);
        assert(pcm.left[SOUND_MIXER_RECLEV]==50 && pcm.left[SOUND_MIXER_IMIX]==100);
        assert(pcm.left[SOUND_MIXER_MONITOR]==100 && pcm.left[SOUND_MIXER_LINE]==100);
        assert(pcm.left[SOUND_MIXER_VOLUME]==95);
    }
    assert(steps.size()==88 && *steps.begin()==0 && *steps.rbegin()==87);
    output.volumeChanged(&left,0,1); output.volumeChanged(&right,0,1); assert(dac.left==1);
    output.volumeChanged(&left,0,50); output.volumeChanged(&right,0,50); assert(dac.left==44);
    output.volumeChanged(&left,0,100); output.volumeChanged(&right,0,100); assert(dac.left==87);
    // Independent stereo controls, mute and resume retain both channel levels.
    output.volumeChanged(&left,0,30); output.volumeChanged(&right,0,80);
    assert(dac.left==26 && dac.right==70);
    output.muteChanged(&left,0,1); assert(speaker.muted==3);
    output.muteChanged(&left,1,0); assert(dac.left==26 && dac.right==70 && !speaker.muted);
    device.mixerResume(&pcm); assert(dac.left==26 && dac.right==70 && !speaker.muted);
    for(int value=0;value<=100;value++) {
        input.volumeChanged(&left,0,value);
        assert(dac.left==26 && dac.right==70 && internal.left==0 && jack.left==0);
    }
    // Off/mismatched topology still uses the old half-range, including its maximum.
    device.mEnableS540OutputRangeFix=false;
    device.audioCtlOssMixerSet(&pcm,SOUND_MIXER_PCM,1,1); assert(dac.left==43);
    device.audioCtlOssMixerSet(&pcm,SOUND_MIXER_PCM,100,100); assert(dac.left==87);
    device.mEnableS540OutputRangeFix=true; dac.size=1;
    device.audioCtlOssMixerSet(&pcm,SOUND_MIXER_PCM,1,1); assert(dac.left==43);
    std::puts("PASS: 88 DAC steps, exact -65.25/0 dB, unchanged maximum, stereo, mute/resume, microphone isolation and topology guards");
}
'''


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: test_audio_output_patch.py /path/to/patched/VoodooHDA')
    source=Path(sys.argv[1])/'tranc'
    engine=(source/'VoodooHDAEngine.cpp').read_text()
    device=(source/'VoodooHDADevice.cpp').read_text()
    functions=[microphone.function(device, signature) for signature in (
        'bool VoodooHDADevice::s540InputGainFixEnabled(',
        'bool VoodooHDADevice::s540OutputRangeFixEnabled(',
        'int VoodooHDADevice::audioCtlOssMixerSet(',
        'int VoodooHDADevice::ilerp(',
        'void VoodooHDADevice::mixerSetDefaults(',
        'void VoodooHDADevice::mixerResume(',
    )]
    functions += [microphone.function(engine, signature) for signature in (
        'UInt64 VoodooHDAEngine::getMinMaxDb(',
        'IOReturn VoodooHDAEngine::volumeChanged(',
        'IOReturn VoodooHDAEngine::muteChanged(',
    )]
    regression=microphone.TESTS.replace('int main() {','int input_regression() {',1)
    regression=regression.rstrip()[:-1]+'\n    return 0;\n}\n'
    compiler=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
    if not compiler: raise SystemExit('A C++ compiler is required')
    with tempfile.TemporaryDirectory(prefix='s540-output-policy-') as temporary:
        cpp=Path(temporary)/'policy.cpp'; exe=Path(temporary)/'policy-test'
        cpp.write_text(STUBS+'\n\n'.join(functions)+regression+OUTPUT_TESTS)
        subprocess.run([compiler,'-std=c++14','-Wall','-Wextra','-Wno-unused-parameter',
                        '-Wno-unused-variable','-fsanitize=undefined,address','-fno-omit-frame-pointer',
                        str(cpp),'-o',str(exe)],check=True)
        environment=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                         UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        subprocess.run([str(exe)],env=environment,check=True)


if __name__=='__main__': main()
